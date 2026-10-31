# -*- coding: utf-8 -*-
"""Сборщик дайджеста площадкам: несколько событий одним письмом.

    docker exec finance_backend python -m app.notify.outward.digest [--dry-run]

Крон: раз в час. Точность до часа здесь достаточна — пачка, обещанная к девяти утра,
уйдёт в интервале 09:00–09:59, и это ровно то, чего ждёт получатель.

## Почему это отдельная задача, а не флаг у досылки

`mail.flush` выпускает ГОТОВЫЕ письма, у которых настал `send_after`, — по одному, как
их сочинили. Дайджест другой по существу: он СОБИРАЕТ несколько событий в одно письмо, и
собрать его из уже отрисованных писем нельзя. Поэтому в очереди лежит содержимое
события, а не HTML.

## Что здесь было до 15.09.2026

`mail/render.py::composed_html` (через `mail/live.py`) — шапка со счётчиками, карточки по тяжести тона — написан с
13.09 и **не вызывался никем**. Рисовать пачку было чем, собирать нечем, и слово
«дайджест» в каталоге видов означало на деле «письмо придержится до девяти утра», по
отдельному письму на событие. Эта задача закрывает разрыв.

## Группировка — по АДРЕСУ, а не по площадке

Один человек ведёт несколько площадок: три письма в девять утра вместо одного — это ровно
то, от чего дайджест и спасает. Площадка при этом не теряется: она стоит в контексте
каждой карточки.
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import timez
from app.database import SessionLocal
from app.mail import client as mail
from app.mail import render
from app.mail.send import send_and_log
from app.notify.outward.send import HAS_CABINET_ACCESS
import app.model_registry  # noqa: F401 — крон отдельным процессом: все таблицы для внешних ключей

log = logging.getLogger("finance.cabinet.digest")

KIND_DIGEST = "pub_digest"      # вид письма в журнале почты
BATCH = 500                     # столько строк очереди разгребаем за прогон

# Порог давности пачки. Его здесь не было ВОВСЕ — замечено 31.10.2026: строка, получатель
# которой вернёт доступ через месяц, уехала бы дайджестом за позапрошлый октябрь. У
# телеграм-досылки такой порог есть с рождения (48 ч) ровно по той же причине:
# «напоминание, доставленное через неделю, хуже недоставленного». Берём те же двое суток —
# это две пропущенные пачки; дальше начинается разбор истории, а он делается не письмом.
MAX_AGE_HOURS = 48


def close_reason(*, age_hours: float, can_receive: bool,
                 why_blocked: Optional[str] = None,
                 max_age_hours: int = MAX_AGE_HOURS) -> Optional[str]:
    """Причина закрыть строку очереди навсегда, или None — строка ещё живая.

    Закрываем ТОЛЬКО по давности, а не в первый же промах получателя: доступ
    возвращается (контакту заводят учётку), и свежую пачку надо отдать, а не похоронить.
    Поэтому промах сам по себе строку не закрывает — закрывает истёкший порог.

    А вот причина пишется НАСТОЯЩАЯ. «Протухло» на строке, получатель которой вообще не
    мог её получить, отправило бы чинить очередь вместо данных получателя.

    Вынесено чистой функцией: это единственное место, где легко перепутать «ещё ждёт» с
    «уже не уйдёт», и проверяется оно без базы.
    """
    if age_hours < max_age_hours:
        return None
    if not can_receive:
        return why_blocked or "получатель не принимает уведомления"
    return f"протухло: пачка старше {max_age_hours} ч"


def _blocker(r) -> Optional[str]:
    """Что именно мешает получателю — словом, а не кодом. Порядок от частного к общему:
    первая названная причина и есть та, которую пойдут чинить."""
    if not r.contact_alive:
        return "контакт удалён"
    if not r.notify_on:
        return "контакт снял «получает уведомления»"
    if not r.has_access:
        return "получатель без учётки кабинета"
    if not r.pub_live:
        return "площадка в архиве"
    if not r.cab_live:
        return "кабинет приостановлен"
    return None


def _close_stale(db: Session, dry_run: bool = False) -> int:
    """Закрыть строки, которые уже не уйдут, и записать ПОЧЕМУ.

    Без этого `sent_at IS NULL` означало сразу две разные вещи — «ждёт своего часа» и
    «не уйдёт никогда», — и отличить их было нечем. Замер на проде 31.10.2026: 22 строки
    третьи сутки, 17 из них отрезаны условием доступа, добавленным 29.10.2026 уже после
    того, как они встали в очередь.

    Флаги получателя берутся по отдельности, а не одним «можно/нельзя»: иначе причину
    пришлось бы угадывать, а она и есть самое полезное в закрытой строке.

    `dry_run` — только посчитать: пробный запуск ничего не меняет, а закрытие строки — навсегда
    (ревью 31.10.2026).
    """
    rows = db.execute(text(f"""
        SELECT q.id,
               EXTRACT(EPOCH FROM (now() - q.due_at)) / 3600.0 AS age_hours,
               EXISTS (SELECT 1 FROM sales_publisher_contacts c
                        WHERE c.id = q.contact_id)                        AS contact_alive,
               EXISTS (SELECT 1 FROM sales_publisher_contacts c
                        WHERE c.id = q.contact_id AND c.notify)           AS notify_on,
               EXISTS (SELECT 1 FROM sales_publisher_contacts c
                        WHERE c.id = q.contact_id AND {HAS_CABINET_ACCESS}) AS has_access,
               EXISTS (SELECT 1 FROM sales_publishers p
                        WHERE p.id = q.publisher_id AND p.status <> 'АРХИВ') AS pub_live,
               NOT EXISTS (SELECT 1 FROM cabinet_publisher cp
                             JOIN cabinet cab ON cab.id = cp.cabinet_id
                            WHERE cp.publisher_id = q.publisher_id
                              AND cab.state = 'приостановлен')            AS cab_live
          FROM cabinet_digest_queue q
         WHERE q.sent_at IS NULL AND q.closed_reason IS NULL
           AND q.due_at < now() - make_interval(hours => :cap)
         ORDER BY q.id
    """), {"cap": MAX_AGE_HOURS}).fetchall()
    closed = 0
    for r in rows:
        why = _blocker(r)
        reason = close_reason(age_hours=float(r.age_hours), can_receive=why is None,
                              why_blocked=why)
        if not reason:
            continue
        closed += 1
        if dry_run:
            continue
        db.execute(text("UPDATE cabinet_digest_queue SET closed_reason = :r WHERE id = :i"),
                   {"r": reason[:300], "i": r.id})
    if closed and not dry_run:
        db.commit()
        log.info("Очередь дайджеста: закрыто строк по давности — %s", closed)
    return closed


class _Busy(RuntimeError):
    pass


def run(dry_run: bool = False) -> dict:
    """Разослать пачки, чей час настал. Возвращает счётчики.

    Один прогон за раз (аудит 23.09.2026, 5.L4): наложившиеся прогоны выбирали одни и
    те же строки очереди, и площадка получала дайджест дважды.
    """
    from app.ext_lock import OUTWARD_DIGEST, only_one
    try:
        with only_one(OUTWARD_DIGEST, 1, _Busy, "Дайджест площадкам"):
            return _run(dry_run)
    except _Busy:
        print("дайджест площадкам: предыдущий прогон ещё идёт — этот пропускаю")
        return {"due": 0, "letters": 0, "sent": 0, "failed": 0, "busy": True}


def _run(dry_run: bool) -> dict:
    """Каждый адрес считается отдельно: отказ по одному не отменяет остальных — то же
    правило, что в пакетной отправке гейта и в досылке, и по той же причине."""
    db = SessionLocal()
    stats = {"due": 0, "letters": 0, "sent": 0, "failed": 0, "closed": 0}
    try:
        if not mail.configured():
            print("почта не настроена — дайджест собирать некуда")
            return stats

        # Сначала закрыть протухшее, потом собирать: иначе строка за позапрошлую неделю
        # попала бы в сегодняшнюю пачку, а это ровно то, от чего порог и ставится.
        stats["closed"] = _close_stale(db, dry_run=dry_run)

        rows = db.execute(text(f"""
            SELECT id, publisher_id, contact_id, email, to_name, kind, title, body,
                   context, link_abs, facts, tone, tag, created_at
              FROM cabinet_digest_queue q
             WHERE sent_at IS NULL AND closed_reason IS NULL AND due_at <= now()
               -- Накопленное до приостановки кабинета тоже не уходит (ревью 23.09.2026).
               AND NOT EXISTS (
                   SELECT 1 FROM cabinet_publisher cp JOIN cabinet cab ON cab.id = cp.cabinet_id
                    WHERE cp.publisher_id = q.publisher_id AND cab.state = 'приостановлен')
               -- Контакт снял «получает уведомления» или удалён после постановки — его
               -- накопленное не уходит (аудит 01.10.2026, С-6); учётку выключили — тоже (29.10.2026).
               AND EXISTS (SELECT 1 FROM sales_publisher_contacts c
                            WHERE c.id = q.contact_id AND c.notify AND {HAS_CABINET_ACCESS})
               -- Площадку перевели в архив после постановки — накопленное не уходит (В-8).
               AND EXISTS (SELECT 1 FROM sales_publishers p
                            WHERE p.id = q.publisher_id AND p.status <> 'АРХИВ')
             ORDER BY due_at, id
             LIMIT :n"""), {"n": BATCH}).fetchall()
        stats["due"] = len(rows)
        if not rows:
            print("к отправке ничего нет")
            return stats

        by_addr = defaultdict(list)
        for r in rows:
            by_addr[r.email].append(r)

        from app.mail import live

        brand = mail.sender_name()
        for email, items in by_addr.items():
            to_name = next((r.to_name for r in items if r.to_name), "")
            cards = [live.card(db, "pub", r.kind, _card(r), {}, fields=live.LOOK)
                     for r in items]
            # Площадка в подстановке — только когда пачка про ОДНУ площадку: у сети
            # сайтов адрес один на несколько, и назвать одну из них значило бы соврать.
            pubs = {r.publisher_id for r in items}
            pub_name = (db.execute(text("SELECT name FROM sales_publishers WHERE id = :p"),
                                   {"p": next(iter(pubs))}).scalar() or ""
                        if len(pubs) == 1 else "")
            # Шапка, тема и подвал — оболочка «Шаблонов писем», тем же сборщиком, что
            # рисует предпросмотр (аудит 23.09.2026, 5.M1).
            subject, html = live.digest(
                db, "pub", cards, {"имя": to_name or "коллеги", "площадка": pub_name},
                brand=brand, logo_url=render.cabinet_url(render.LOGO_PATH),
                settings_url=render.cabinet_url("/"))
            # Текстовая часть — из тех же карточек, что разметка: кнопку убрали в
            # редакторе — ссылки нет и в тексте.
            body = "\n\n".join(
                render.text_body(c["title"] if not c.get("context")
                                 else f"{c['title']}\n{c['context']}",
                                 c.get("body"), c.get("link_abs"), c.get("facts") or [])
                for c in cards)

            if dry_run:
                print(f"  [сухой] {email}: {len(items)} событий — {subject}")
                stats["letters"] += 1
                continue

            row = send_and_log(db, to=email, to_name=to_name, subject=subject[:200],
                               body=body, html=html, kind=KIND_DIGEST,
                               entity_type="cabinet_digest", entity_id=items[0].id)
            stats["letters"] += 1
            if row.status == "sent":
                stats["sent"] += len(items)
            else:
                stats["failed"] += len(items)
                log.warning("Дайджест на %s не ушёл: %s", email, row.error)

            # Помечаем отправленным ДАЖЕ ПРИ ОТКАЗЕ, и это осознанно: письмо уже лежит в
            # журнале почты со своим статусом, и повторная сборка завтра прислала бы
            # вчерашние события второй раз. Неудачная доставка разбирается через журнал
            # писем — там есть и адрес, и причина, — а не повторным накоплением.
            db.execute(text("UPDATE cabinet_digest_queue "
                            "   SET sent_at = now(), mail_log_id = :m "
                            " WHERE id = ANY(:ids)"),
                       {"m": row.id, "ids": [r.id for r in items]})
            db.commit()

        print(f"дайджест: событий {stats['due']}, писем {stats['letters']}, "
              f"доставлено событий {stats['sent']}, не доставлено {stats['failed']}, "
              f"{'закрылось бы' if dry_run else 'закрыто'} по давности {stats['closed']}")
        return stats
    finally:
        db.close()


def _card(r) -> dict:
    """Карточка пачки для площадки.

    Час события — МОСКОВСКИЙ: `created_at` в очереди лежит в UTC, и площадка читала
    06:14 о событии, случившемся у неё в 09:14 (аудит 23.09.2026). Дайджест сотрудникам
    переводил время с самого начала; здесь перевод забыли.
    """
    return {
        "title": r.title, "body": r.body, "link_abs": r.link_abs,
        "tone": r.tone or "info", "tag": r.tag or "",
        "context": r.context,
        # Час события, а не час письма: в пачке из шести карточек «когда это
        # случилось» — половина смысла.
        "when": timez.to_msk(r.created_at).strftime("%H:%M") if r.created_at else "",
        "facts": [tuple(f) for f in (r.facts or [])],
        "action": "Открыть кабинет",
        "needs_action": _needs_action(getattr(r, "kind", None)),
    }


def _needs_action(kind_key) -> bool:
    from app.notify.outward.kinds import by_key
    k = by_key(kind_key)
    return bool(k and k.needs_action)


def _plural(n: int) -> str:
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
