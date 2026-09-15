# -*- coding: utf-8 -*-
"""Прослойка рассылки ПЛОЩАДКАМ: одна точка, через которую уходит наружу.

Каталог видов (`notify_kinds.py`) объявлял шестнадцать сообщений, а отправлял их никто —
кроме запроса посадочной, написанного отдельно и целиком вручную. Здесь то, чего не
хватало: место, куда приходит «случилось вот это по такой-то площадке», а дальше уже
общий порядок — можно ли слать, кому, чем и с какой записью в журнале.

## Почему отдельно от `notify/bus.py`

Внутренняя шина адресует СОТРУДНИКОВ: резолверы ролей, профили подписки, тихие часы,
телеграм. Здесь всё другое: получатель — контакт площадки, подписка жёстко задана нами,
канал один, а содержимое проходит через границу контура. Общего у них только гейт почты,
и он общий и есть.

Слить их в одну шину значило бы завести в коде, адресующем сотрудников, ветку «а если это
не сотрудник» — и рано или поздно письмо ушло бы наружу по внутреннему правилу.

## Порядок проверок и почему он такой

1. **вид объявлен** — иначе это ошибка программиста, и она должна падать, а не молчать;
2. **вид построен** (`built`) — отправка непостроенного вида означала бы, что каталог
   врёт; признак и отправитель обязаны появляться вместе;
3. **вид включён нами** — вкладка «Кабинеты → Что мы шлём»;
4. **почта настроена** — иначе некуда;
5. **площадка не выключила** — её собственный выключатель, последним по счёту: наши
   решения старше её предпочтений, но её предпочтение старше самого письма.

Каждый отказ возвращается СЛОВОМ, а не тишиной: «письмо не ушло» без причины разбирается
заново каждый раз.

## Адресат: сегодня один на всех

Каталог различает аккаунта площадки, техподдержку и бухгалтерию. Наши данные этого
различия не знают: в `sales_publisher_contacts` роль — свободная строка с должностью
(«Ведущий интернет-маркетолог»), и заполнена она у одного контакта из сорока пяти.
Поэтому письмо уходит ОСНОВНОМУ контакту, какой бы адресат ни был объявлен, а объявленный
пишется в журнал. Молча выбирать «бухгалтерию» из должностей нельзя: письмо про оплату
ушло бы маркетологу, и заметил бы это только он.

Когда у контактов появится функциональная роль, менять придётся одну функцию —
`_recipients`, и это будет правка схемы, согласованная до кода.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.notify.outward.kinds import by_key

log = logging.getLogger("finance.cabinet.notify")

KIND_PUB = "pub_notify"          # вид письма в журнале почты


def _enabled(db: Session, key: str) -> bool:
    from app.routers.cabinets import _notify_off
    return key not in _notify_off(db)


def _muted_accounts(db: Session, publisher_id: int, key: str) -> set:
    """Учётки площадки, выключившие этот вид. Строка есть — выключено."""
    rows = db.execute(text("""
        SELECT m.account_id FROM cabinet_account_mute m
         WHERE m.kind = :k AND m.account_id IN (
             SELECT a.id FROM cabinet_account a
              JOIN cabinet_publisher cp ON cp.cabinet_id = a.cabinet_id
             WHERE cp.publisher_id = :p)"""), {"k": key, "p": publisher_id}).fetchall()
    return {r[0] for r in rows}


def _recipients(db: Session, publisher_id: int) -> list:
    """Кому писать: контактам с отметкой «получает уведомления».

    Отметка ставится на экране кабинета и заменила прежнее правило «первый по признаку
    основного». То правило опиралось на чужой флаг: `is_primary` отвечает, к кому идти с
    вопросом, а не кому слать почту, и на первом же «главный, но писать ему не надо» они
    разошлись бы.

    Отмеченных может быть НЕСКОЛЬКО — письмо уйдёт каждому. Ни одного — писем нет, и это
    осознанное состояние площадки, а не повод тихо откатиться к основному: молчаливый
    откат сделал бы отметку декоративной.
    """
    rows = db.execute(text("""
        SELECT c.id, c.email, c.name FROM sales_publisher_contacts c
         WHERE c.publisher_id = :p AND c.notify AND coalesce(c.email, '') <> ''
         ORDER BY c.is_primary DESC, c.id"""), {"p": publisher_id}).fetchall()
    return [{"contact_id": r[0], "email": r[1], "name": r[2]} for r in rows]


def notify_publisher(db: Session, kind_key: str, publisher_id: int, *,
                     title: str, body: Optional[str] = None,
                     facts: Iterable[Tuple[str, str]] = (),
                     context: Optional[str] = None,
                     link: Optional[str] = None,
                     entity_type: Optional[str] = None,
                     entity_id: Optional[int] = None) -> dict:
    """Отправить площадке уведомление вида `kind_key`.

    Возвращает `{"status": …, "why": …}`. Исключение НЕ поднимается: вызывающий делает
    своё дело (двигает пару, проводит платёж), и несостоявшееся письмо не должно это
    отменять. Причина уходит в ответ и в журнал.

    `context` — строка «домен · кампания · период»: у площадки одновременно идут
    несколько кампаний, и «ваш креатив ждёт решения» без неё бесполезно. НАШЕГО кода
    сделки в ней нет и быть не может — граница контура.
    """
    from app.mail import client as mailc
    from app.mail import render
    from app.mail.send import send_and_log

    kind = by_key(kind_key)
    if kind is None:
        raise ValueError(f"вида «{kind_key}» нет в каталоге рассылки площадкам")
    if not kind.built:
        # Отправитель есть, а признак не поставлен — каталог врёт экрану «Что мы шлём».
        raise ValueError(f"вид «{kind_key}» не помечен built, а отправка уже написана")
    if not _enabled(db, kind_key):
        return {"status": "off", "why": "вид выключен нами"}
    if not mailc.configured():
        return {"status": "off", "why": "почта не настроена"}

    to = _recipients(db, publisher_id)
    if not to:
        return {"status": "no_address", "why": "у площадки нет контакта с почтой"}

    # Выключатель площадки. Он на учётке, а письмо — контакту, и связь между ними
    # непрямая: выключено считается, когда выключили ВСЕ учётки кабинета. Иначе одна
    # учётка, снявшая галочку, заглушила бы письмо остальным.
    if kind.can_mute:
        muted = _muted_accounts(db, publisher_id, kind_key)
        total = db.execute(text("""
            SELECT count(*) FROM cabinet_account a
             JOIN cabinet_publisher cp ON cp.cabinet_id = a.cabinet_id
            WHERE cp.publisher_id = :p AND a.is_active"""), {"p": publisher_id}).scalar()
        if total and len(muted) >= total:
            return {"status": "muted", "why": "площадка выключила этот вид"}

    # Тихие часы площадки. Срочные виды не будят ночью тоже: снаружи мы не сотрудники
    # друг другу, и ночное письмо от подрядчика читается как невежливость. Разница между
    # срочным и обычным — не «разбудить», а «уйти первым, отдельным письмом».
    from datetime import datetime as _dt

    from app.notify.outward import schedule
    tz = db.execute(text("SELECT timezone_offset FROM sales_publishers WHERE id = :p"),
                    {"p": publisher_id}).scalar()
    now_utc = _dt.utcnow()
    due = schedule.due_at(now_utc, tz, immediate=(kind.schedule == "сразу"))

    import os
    link_abs = render.abs_url(link)
    html = render.notification_html(
        title=title, body=body, link_abs=link_abs, tone=kind.tone,
        # Время в шапке — по часам ПЛОЩАДКИ, а не по нашим: письмо читает она, и
        # «получено в 04:12» у владивостокского контакта выглядит как ночная рассылка.
        when=schedule.publisher_now(now_utc, tz),
        tag=kind.tag or kind.label, action="Открыть кабинет", facts=facts,
        context=context, logo_url=render.abs_url(render.LOGO_PATH),
        brand=(os.getenv("MAIL_FROM_NAME") or "SIMB-AD").strip())
    subject = title if not context else f"{title} · {context}"

    # Отмеченных контактов может быть несколько — письмо уходит КАЖДОМУ, и каждый
    # считается отдельно: отказ по одному адресу не отменяет остальных (то же правило,
    # что в пакетной отправке гейта, и по той же причине).
    head = title if not context else title + chr(10) + context
    text_part = render.text_body(head, body, link_abs, facts)
    sent, failed, held = [], [], []
    for r in to:
        row = send_and_log(db, to=r["email"], to_name=r["name"], subject=subject[:200],
                           body=text_part, html=html, kind=KIND_PUB, send_after=due,
                           entity_type=entity_type, entity_id=entity_id)
        if due is not None:
            held.append(r["email"])
            continue
        (sent if row.status == "sent" else failed).append(
            {"to": r["email"], "id": row.id, "error": row.error})
        if row.status != "sent":
            log.warning("Площадке %s не ушло «%s» на %s: %s",
                        publisher_id, kind_key, r["email"], row.error)
    if held:
        return {"status": "held", "why": "тихие часы площадки",
                "due": due.isoformat(), "held": held, "intended_to": kind.to}
    return {"status": "sent" if sent else "failed",
            "why": "" if sent else (failed[0]["error"] if failed else ""),
            "sent": [x["to"] for x in sent], "failed": failed,
            "intended_to": kind.to}
