# -*- coding: utf-8 -*-
"""Сборщик дайджеста СОТРУДНИКАМ: несколько уведомлений одним письмом.

    docker exec finance_backend python -m app.notify.digest [--dry-run]

Крон: раз в час. Точность до часа достаточна — пачка, обещанная к 09:30, уйдёт в
интервале своего часа, и это ровно то, чего ждёт получатель.

## Что здесь было до 16.09.2026

Канал «дайджест» существовал на экране и в подписках с рождения модуля, но в шине
`LIVE_CHANNELS = {app, tg, mail}` — и всё, что человек переводил в дайджест, ложилось в
журнал статусом `queued` и не уходило НИКОГДА. Поломка тихая вдвойне: галочка стоит,
журнал зелёный, писем нет. Отдельно опасная тем, что у событий с `locked=True` дайджест —
единственный разрешённый способ приглушить поток: «нельзя отключить, можно перевести в
дайджест». То есть человек, воспользовавшийся единственной законной дверью, переставал
получать событие вовсе.

## Очередь — это журнал отправок, отдельной таблицы нет

Так объявлено в модели (`NotificationDelivery`: «он же очередь дайджеста»), и это верно:
в строке уже лежит всё, из чего собирается карточка — заголовок, тело, ссылка, факты,
код. Заводить вторую таблицу значило бы держать два описания одного события.

Отличие от внешнего контура (`outward/digest.py`), где очередь своя: там событие
адресовано КОНТАКТУ площадки, у которого нет учётки и нет строки в журнале отправок.

## Час у каждого свой, и считается он от СОБЫТИЯ, а не от прогона

Уведомление, случившееся в 14:00 при часе пачки 09:30, ждёт УТРА СЛЕДУЮЩЕГО ДНЯ, а не
уходит ближайшим прогоном. Иначе «дайджест» означал бы «письмо с задержкой до часа», и
человек получал бы их столько же, сколько событий, — то есть ровно то, от чего уходил.

Часы МОСКОВСКИЕ (`timez.msk_now`). Контейнер живёт в UTC, и час, заданный человеком,
без этого сдвигался бы на три — та же ловушка, что уже ловила тихие часы дважды.
"""
from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import timez
from app.database import SessionLocal
from app.mail import client as mail
from app.mail import render
from app.models import User
from app.notify import channels
from app.notify import registry
from app.notify import tone as tone_of
from app.notify.models import NotificationDelivery, UserNotificationChannels

log = logging.getLogger("finance.notify.digest")

BATCH = 500                  # столько строк очереди разгребаем за прогон
DEFAULT_HOUR, DEFAULT_MINUTE = 9, 30


def _digest_time(ch: UserNotificationChannels | None) -> tuple:
    """Час и минута пачки. Значения по умолчанию совпадают с тем, что отдаёт `/me`."""
    if ch is None:
        return DEFAULT_HOUR, DEFAULT_MINUTE
    h = ch.digest_hour if ch.digest_hour is not None else DEFAULT_HOUR
    m = ch.digest_minute if ch.digest_minute is not None else DEFAULT_MINUTE
    return max(0, min(23, int(h))), max(0, min(59, int(m)))


def due_at(created_at: datetime, hour: int, minute: int) -> datetime:
    """Ближайший час пачки СТРОГО ПОСЛЕ момента события. Момент — уже МОСКОВСКИЙ:
    перевод делает вызывающий, чтобы в этой функции не было второй точки перевода.

    Отдельной функцией, потому что на неё стоит прибор: правило «событие в 14:00 уходит
    завтра утром» глазами из кода не читается, а ошибка в нём выглядит как «дайджест
    приходит слишком часто» — и разбирается уже по жалобе.
    """
    when = created_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if created_at >= when:
        when += timedelta(days=1)
    return when


def _cards(rows) -> list:
    """Карточки для вёрстки пачки. Тон и раздел берутся у реестра по ключу события:
    в журнале их нет, а в письме они несут смысл — отказ и напоминание не одно и то же.
    """
    out = []
    for r in rows:
        ev = registry.get(r.event_key)
        out.append({
            "title": r.title or "", "body": r.body, "link_abs": render.abs_url(r.link),
            "tone": tone_of.norm(getattr(ev, "tone", None)) if ev else "info",
            "tag": (getattr(ev, "group", "") or "") if ev else "",
            "context": "",
            # Час события, а не час письма: в пачке из шести карточек «когда это
            # случилось» — половина смысла.
            "when": timez.to_msk(r.created_at).strftime("%H:%M") if r.created_at else "",
            "facts": [tuple(f) for f in (r.facts or [])],
            "action": (getattr(ev, "action", "") or "Открыть") if ev else "Открыть",
        })
    return out


def run(dry_run: bool = False) -> dict:
    """Разослать пачки, чей час настал. Возвращает счётчики.

    Каждый получатель считается отдельно: отказ по одному не отменяет остальных — то же
    правило, что в гейте, в досылке и во внешнем дайджесте, и по той же причине.
    """
    db: Session = SessionLocal()
    stats = {"queued": 0, "due": 0, "letters": 0, "sent": 0, "failed": 0}
    try:
        if not mail.configured():
            print("почта не настроена — дайджест собирать некуда")
            return stats

        rows = (db.query(NotificationDelivery)
                .filter(NotificationDelivery.channel == "digest",
                        NotificationDelivery.status == "queued")
                .order_by(NotificationDelivery.created_at, NotificationDelivery.id)
                .limit(BATCH).all())
        stats["queued"] = len(rows)
        if not rows:
            print("очередь дайджеста пуста")
            return stats

        now = timez.msk_now()
        by_user = defaultdict(list)
        for r in rows:
            by_user[r.user_id].append(r)

        brand = (os.getenv("MAIL_FROM_NAME") or "SIMB-AD").strip()
        for uid, all_rows in by_user.items():
            u = db.query(User).filter(User.id == uid).first()
            ch = (db.query(UserNotificationChannels)
                  .filter(UserNotificationChannels.user_id == uid).first())
            addr = (ch.mail_override if ch and ch.mail_override else (u.email if u else "")) or ""
            hour, minute = _digest_time(ch)
            # `created_at` в базе — UTC, а час пачки человек задавал МОСКОВСКИЙ.
            # Сравнивать их напрямую значит ошибиться на три часа: пачка уходила бы
            # в 06:30 вместо 09:30, и выглядело бы это правдоподобно.
            items = [r for r in all_rows
                     if r.created_at
                     and due_at(timez.to_msk(r.created_at), hour, minute) <= now]
            if not items:
                continue
            stats["due"] += len(items)

            # Адрес проверяем ПОСЛЕ отбора по времени: «некому слать» — это состояние
            # получателя, и в счётчик «не доставлено» оно должно попадать вместе с
            # числом событий, а не молча.
            if not mail.valid_address(addr):
                log.warning("Дайджест для user_id=%s не собран: нет адреса", uid)
                stats["failed"] += len(items)
                continue

            cards = _cards(items)
            html = render.digest_html(items=cards, to_name=getattr(u, "name", "") or "",
                                      brand=brand, logo_url=render.abs_url(render.LOGO_PATH))
            # Тема НАЗЫВАЕТ ЧИСЛО: «уведомления» без числа неотличимо от одного события.
            subject = f"{len(items)} {plural(len(items))}"
            body = "\n\n".join(
                render.text_body(c["title"], c["body"], c["link_abs"], c["facts"])
                for c in cards)

            if dry_run:
                print(f"  [сухой] {addr}: {len(items)} событий — {subject}")
                stats["letters"] += 1
                continue

            stats["letters"] += 1
            # Отправляем ЧЕРЕЗ КАНАЛ, а не гейтом напрямую: доставка живёт в
            # `channels.py`, здесь — правила «кому и когда». Первая редакция звала гейт
            # сама, и прибор `test_delivery_is_not_duplicated_by_the_contours` это поймал.
            status, _, err = channels.deliver_digest(
                to=addr, to_name=getattr(u, "name", None), subject=subject,
                text=body, html=html).partition("|")
            err = err or None
            if status == "sent":
                stats["sent"] += len(items)
            else:
                stats["failed"] += len(items)
                log.warning("Дайджест на %s не ушёл: %s", addr, err)

            # Строки помечаются исходом ОДИН РАЗ — и при отказе тоже. Оставить их в
            # очереди значило бы прислать завтра вчерашнее второй раз; неудача
            # разбирается по журналу почты, где есть и адрес, и причина.
            for r in items:
                r.status, r.error = status, err
            db.commit()

        print(f"дайджест сотрудникам: в очереди {stats['queued']}, "
              f"к отправке {stats['due']}, писем {stats['letters']}, "
              f"доставлено событий {stats['sent']}, не доставлено {stats['failed']}"
              + (", сухой прогон" if dry_run else ""))
        return stats
    finally:
        db.close()


def plural(n: int) -> str:
    """«1 уведомление · 2 уведомления · 5 уведомлений» — по-русски, а не «1 уведомлений».

    Тема письма — первое, что видит человек, и ошибка согласования в ней читается как
    машинная рассылка, которую можно не открывать.
    """
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return "уведомление"
    if n10 in (2, 3, 4) and n100 not in (12, 13, 14):
        return "уведомления"
    return "уведомлений"


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
