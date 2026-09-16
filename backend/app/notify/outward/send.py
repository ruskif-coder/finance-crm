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
from datetime import datetime
from typing import Iterable, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.notify.outward import prefs
from app.notify.outward.kinds import by_key

log = logging.getLogger("finance.cabinet.notify")

KIND_PUB = "pub_notify"          # вид письма в журнале почты

# ДЕНЕГ В ПИСЬМЕ ПЛОЩАДКЕ НЕТ НИКОГДА (правило владельца 16.09.2026). Это не про
# аккуратность формулировок: наши суммы — это наша маржа и наши условия с клиентом, и
# площадке они не принадлежат. Сверху стоит заслон, а не только договорённость: любой
# будущий отправитель может передать сумму по невнимательности, и заметит это площадка.
#
# Заслон СНИМАЕТ плашку и пишет в лог, а не роняет отправку: письмо про сорванный старт
# важнее, чем идеальный состав его плашек.
MONEY_WORDS = ("сумм", "цена", "стоим", "бюджет", "оплат", "деньг", "руб", "₽",
               "cpm", "cpc", "ставк", "тариф", "прайс")


def strip_money(facts) -> list:
    """Убрать из плашек всё, что называет деньги. Ключ И значение: «за размещение» с
    значением «500 000 ₽» прошло бы проверку по одному ключу."""
    out = []
    for f in (facts or []):
        k = str(f[0] if isinstance(f, (list, tuple)) else f).lower()
        v = str(f[1] if isinstance(f, (list, tuple)) and len(f) > 1 else "").lower()
        if any(w in k or w in v for w in MONEY_WORDS):
            log.warning("Из письма площадке убрана денежная плашка: %s", f)
            continue
        out.append(tuple(f) if isinstance(f, (list, tuple)) else (f, ""))
    return out


def _enabled(db: Session, key: str) -> bool:
    from app.routers.cabinets import _notify_off
    return key not in _notify_off(db)


# `_muted_accounts` удалён 15.09.2026 вместе с переездом на матрицу «событие × канал».
# Таблица `cabinet_account_mute` заморожена (правило проекта: устаревшее не дропается), но
# читателей у неё больше нет — оставить функцию значило бы держать второй ответ на вопрос
# «выключено ли», который однажды разошёлся бы с первым.


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


# Вид рассылки -> событие ленты. Пара, а не вывод из ключа: оба ключа неизменяемы и
# должны находиться поиском. Выведенный ключ нельзя ни найти, ни проверить прибором
# «у события есть производитель» — он бы и не нашёл этот файл.
JOURNAL_ACTION = {
    'новый креатив': 'увед_новый_креатив',
    'запрос ссылки': 'увед_запрос_ссылки',
    'ерид выпущен': 'увед_ерид',
    'старт рк': 'увед_старт_рк',
}

# Автор строки ленты для того, что отправила система. Живого человека здесь нет, и
# подставлять имя аккаунта было бы неправдой: письмо ушло по правилу, а не по чьему-то
# решению.
ACTOR_AUTO = "автоматически"


def _to_panel(db: Session, kind_key: str, publisher_id: int, *, title: str,
              context: Optional[str], entity_type: Optional[str],
              entity_id: Optional[int]) -> str:
    """Панель кабинета. Первая и БЕЗУСЛОВНАЯ — её нельзя выключить.

    Своей таблицы у панели нет: `cabinet_log` объявлен журналом с двумя читателями, и
    второй список тех же событий разошёлся бы с первым молча.

    Пишется ДО проверок почты и бота: выключенная почта не означает, что события не
    было. Отсюда же и `commit` здесь, а не только в отправителе письма, — иначе на ветке
    «почта не настроена» строка панели терялась бы вместе с транзакцией.
    """
    from app.cabinet import journal

    action = JOURNAL_ACTION.get(kind_key)
    if action is None:
        # Вид построен, а события ленты у него нет. Это долг, а не норма: прибор
        # `tests/test_cabinet_feed.py` держит пары полными.
        return "no_action"
    cab = journal.cabinet_of_publisher(db, publisher_id)
    if not cab:
        return "no_cabinet"      # площадка не привязана к кабинету — ленту читать некому
    journal.write(db, action, cabinet_id=cab, publisher_id=publisher_id,
                  actor_name=ACTOR_AUTO, subject=(context or title),
                  entity_type=entity_type, entity_id=entity_id)
    db.commit()
    return "ok"


def _to_bot(db: Session, kind, publisher_id: int, *, title: str, body: Optional[str],
            facts, context: Optional[str], link: Optional[str]) -> dict:
    """Бот площадки. Получают те учётки, кто привязал его СЕБЕ САМ.

    Галочка «получает уведомления» с карточки контакта здесь не работает — она про почту
    (решение владельца 15.09.2026). Бота мы за человека подключить не можем, поэтому
    список получателей свой: у кого есть подтверждённый чат.

    ТИХИЕ ЧАСЫ СОБЛЮДАЮТСЯ, и сообщение при этом не откладывается, а не уходит вовсе —
    очереди у бота пока нет, в отличие от почты. Потерей это не является: то же событие
    уже лежит в панели, и человек увидит его, открыв кабинет. Отложенная доставка бота
    появится вместе с накопителем дайджеста.
    """
    from datetime import date

    from app.notify import telegram
    from app.notify.channels import tg_text
    from app.notify.outward import schedule

    if not telegram.configured(telegram.PUB):
        return {"status": "no_channel", "sent": 0}

    rows = db.execute(text("""
        SELECT t.account_id, t.chat_id, t.mute_until
          FROM cabinet_account_tg t
          JOIN cabinet_account a ON a.id = t.account_id AND a.is_active
          JOIN cabinet_publisher cp ON cp.cabinet_id = a.cabinet_id
         WHERE cp.publisher_id = :p
           AND t.verified_at IS NOT NULL AND coalesce(t.chat_id, '') <> ''"""),
        {"p": publisher_id}).fetchall()
    if not rows:
        return {"status": "no_channel", "sent": 0}

    tz = db.execute(text("SELECT timezone_offset FROM sales_publishers WHERE id = :p"),
                    {"p": publisher_id}).scalar()
    _, q_from, q_to = schedule.hours(db)
    if schedule.in_quiet_hours(schedule.publisher_now(datetime.utcnow(), tz), q_from, q_to):
        return {"status": "quiet_hours", "sent": 0}

    off = prefs.off_accounts(db, kind.key, prefs.BOT) if kind.can_mute else set()
    today = date.today()
    head = title if not context else title + chr(10) + context
    msg = tg_text(head, body, facts)
    sent, failed = 0, []
    for r in rows:
        if r.account_id in off:
            continue
        if r.mute_until and r.mute_until >= today:
            continue
        try:
            telegram.send_message(r.chat_id, msg, link=link, contour=telegram.PUB)
            sent += 1
        except Exception as e:   # noqa: BLE001 — причина в лог, доставка остальным не отменяется
            failed.append(str(e)[:200])
            log.warning("Площадке %s не ушёл бот «%s»: %s", publisher_id, kind.key, e)
    return {"status": "sent" if sent else ("failed" if failed else "muted"),
            "sent": sent, "failed": failed}


def _to_digest(db: Session, publisher_id: int, rcpt: dict, *, kind, title: str,
               body: Optional[str], context: Optional[str], link_abs: Optional[str],
               facts, tz, now_utc) -> dict:
    """Положить событие в накопитель дайджеста.

    В очередь едет СОДЕРЖИМОЕ, а не готовое письмо: пачка собирается из карточек, и
    сохранённый HTML одного письма в неё не складывается.

    Час ОДИН НА ВСЕХ — 09:00 по времени площадки (`schedule.DIGEST_HOUR`), и смещение
    берётся из её карточки. Хранится срок в нашей шкале, как `send_after` у письма:
    переводить туда-обратно в момент отправки значило бы делать это дважды и однажды
    ошибиться знаком.
    """
    import json

    from app.notify.outward import schedule

    due = schedule.next_hour_at(now_utc, tz, schedule.hours(db)[0])
    db.execute(text("""
        INSERT INTO cabinet_digest_queue
            (publisher_id, contact_id, email, to_name, kind, title, body, context,
             link_abs, facts, tone, tag, due_at)
        VALUES (:p, :c, :e, :n, :k, :t, :b, :ctx, :l, cast(:f as jsonb), :tone, :tag, :due)"""),
        {"p": publisher_id, "c": rcpt["contact_id"], "e": rcpt["email"],
         "n": rcpt["name"], "k": kind.key, "t": title, "b": body, "ctx": context,
         "l": link_abs, "f": json.dumps([list(x) for x in (facts or [])],
                                        ensure_ascii=False),
         "tone": kind.tone, "tag": kind.tag or kind.label, "due": due})
    db.commit()
    return {"due": due.isoformat()}


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
        # Выключено НАМИ — события не было вовсе, поэтому молчат все три канала, включая
        # панель. Это единственная ветка, где панель не пишется.
        return {"status": "off", "why": "вид выключен нами"}

    # ЗАСЛОН ПЕРЕД ВСЕМИ КАНАЛАМИ, а не только перед почтой: бот и панель показывают те
    # же плашки, и «убрали из письма, оставили в телеграме» это не выполненное правило,
    # а его видимость.
    facts = strip_money(facts)

    # Панель и бот — до проверок почты: «почта не настроена» не означает, что события не
    # случилось. Порядок ровно такой, как в матрице кабинета слева направо.
    extra = {
        "panel": _to_panel(db, kind_key, publisher_id, title=title, context=context,
                           entity_type=entity_type, entity_id=entity_id),
        "tg": _to_bot(db, kind, publisher_id, title=title, body=body, facts=facts,
                      context=context, link=link),
    }

    if not mailc.configured():
        return {"status": "off", "why": "почта не настроена", **extra}

    to = _recipients(db, publisher_id)
    if not to:
        return {"status": "no_address", "why": "у площадки нет контакта с почтой", **extra}

    # ── КТО ИЗ ПОЛУЧАТЕЛЕЙ ЧТО ВЫБРАЛ ───────────────────────────────────────
    #
    # До 15.09.2026 выключенным считалось то, что выключили ВСЕ учётки кабинета сразу.
    # Правило родилось из невозможности связать учётку с адресатом и давало странность:
    # один человек снимал галочку и не влиял ни на что. Связь есть — `contact_id` у
    # учётки, — и правило стало прямым: каждый распоряжается СВОЕЙ почтой.
    #
    # Контакт без учётки получает умолчания: настраивать ему негде, а отказывать ему в
    # письме на этом основании было бы худшим из решений — до появления кабинета такие
    # контакты и были единственными получателями.
    acc_of = prefs.accounts_by_contact(db, publisher_id)

    # Тихие часы площадки. Срочные виды не будят ночью тоже: снаружи мы не сотрудники
    # друг другу, и ночное письмо от подрядчика читается как невежливость. Разница между
    # срочным и обычным — не «разбудить», а «уйти первым, отдельным письмом».
    from datetime import datetime as _dt

    from app.notify.outward import schedule
    tz = db.execute(text("SELECT timezone_offset FROM sales_publishers WHERE id = :p"),
                    {"p": publisher_id}).scalar()
    now_utc = _dt.utcnow()
    urgent = kind.schedule == "сразу"
    d_hour, q_from, q_to = schedule.hours(db)
    due = schedule.due_at(now_utc, tz, immediate=urgent,
                          digest=d_hour, quiet_from=q_from, quiet_to=q_to)

    import os
    link_abs = render.abs_url(link)
    html = render.notification_html(
        title=title, body=body, link_abs=link_abs, tone=kind.tone,
        # Время в шапке — по часам ПЛОЩАДКИ, а не по нашим: письмо читает она, и
        # «получено в 04:12» у владивостокского контакта выглядит как ночная рассылка.
        when=schedule.publisher_now(now_utc, tz),
        tag=kind.tag or kind.label, action="Открыть кабинет", facts=facts,
        context=context, logo_url=render.abs_url(render.LOGO_PATH),
        brand=(os.getenv("MAIL_FROM_NAME") or "SIMB-AD").strip(),
        # Адресат — вне компании: подпись и подвал письма говорят про КАБИНЕТ, а
        # ссылка «настроить уведомления» ведёт туда же. Наш /settings/notifications
        # площадке не открыть, и предлагать его — обещание, которого мы не держим.
        audience="pub", settings_url=render.abs_url("/settings"))
    # Тема и словесная часть — ИЗ ШАБЛОНА «Уведомление площадке», правится на экране
    # почты. Вёрстка остаётся кодовой: тон, чип и плашки фактов — это дизайн письма, а
    # не текст, и править их текстом значило бы ломать его первым же переносом строки.
    from app.mail import templates as tpl

    head = title if not context else title + chr(10) + context
    subject, text_part = tpl.apply(
        db, "pub_notify",
        {"заголовок": title, "контекст": context or "", "текст": body or "",
         "факты": render.facts_line(facts), "ссылка": link_abs or ""},
        subject_default=(title if not context else f"{title} · {context}"),
        text_default=render.text_body(head, body, link_abs, facts))

    # Отмеченных контактов может быть несколько — письмо уходит КАЖДОМУ, и каждый
    # считается отдельно: отказ по одному адресу не отменяет остальных (то же правило,
    # что в пакетной отправке гейта, и по той же причине).
    sent, failed, held, queued, muted_out = [], [], [], [], []
    for r in to:
        # РЕШЕНИЕ У КАЖДОГО СВОЁ, и решается оно ПО СОБЫТИЮ, а не по каналу целиком
        # (владелец 15.09.2026): в матрице у почты две колонки — «срочное» и «дайджест».
        # Один человек хочет знать про креатив немедленно, а про старт кампании прочтёт
        # утром; общего ответа тут нет и быть не должно.
        acc_id = acc_of.get(r["contact_id"])
        m = prefs.matrix(db, acc_id) if acc_id else {}
        now_mail = prefs.cell(m, kind, prefs.MAIL)
        in_digest = prefs.cell(m, kind, prefs.DIGEST)

        if not now_mail and not in_digest:
            # Обе колонки сняты — почты по этому событию человек не хочет вовсе.
            muted_out.append(r["email"])
            continue

        # СРОЧНОЕ ИДЁТ МИМО ПАЧКИ — «наше сразу не понижается». Вид, объявленный нами
        # срочным, в дайджест не уходит, даже если галочка каким-то образом там стоит:
        # запрет держится и на записи (ручка), и здесь — на отправке.
        if in_digest and not now_mail and not urgent:
            row = _to_digest(db, publisher_id, r, kind=kind, title=title, body=body,
                             context=context, link_abs=link_abs, facts=facts,
                             tz=tz, now_utc=now_utc)
            queued.append({"to": r["email"], "due": row["due"]})
            continue

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

    if muted_out and not sent and not failed and not held and not queued:
        return {"status": "muted", "why": "площадка выключила этот вид",
                "intended_to": kind.to, **extra}
    if queued and not sent and not failed and not held:
        return {"status": "digest", "why": "уйдёт в дайджесте",
                "queued": queued, "intended_to": kind.to, **extra}
    if held:
        return {"status": "held", "why": "тихие часы площадки",
                "due": due.isoformat(), "held": held, "queued": queued,
                "intended_to": kind.to, **extra}
    return {"status": "sent" if sent else "failed",
            "why": "" if sent else (failed[0]["error"] if failed else ""),
            "sent": [x["to"] for x in sent], "failed": failed, "queued": queued,
            "intended_to": kind.to, **extra}
