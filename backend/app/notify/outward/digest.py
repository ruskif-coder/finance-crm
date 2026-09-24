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

from sqlalchemy import text

from app import timez
from app.database import SessionLocal
from app.mail import client as mail
from app.mail import render
from app.mail.send import send_and_log

log = logging.getLogger("finance.cabinet.digest")

KIND_DIGEST = "pub_digest"      # вид письма в журнале почты
BATCH = 500                     # столько строк очереди разгребаем за прогон


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
    stats = {"due": 0, "letters": 0, "sent": 0, "failed": 0}
    try:
        if not mail.configured():
            print("почта не настроена — дайджест собирать некуда")
            return stats

        rows = db.execute(text("""
            SELECT id, publisher_id, contact_id, email, to_name, kind, title, body,
                   context, link_abs, facts, tone, tag, created_at
              FROM cabinet_digest_queue q
             WHERE sent_at IS NULL AND due_at <= now()
               -- Накопленное до приостановки кабинета тоже не уходит (ревью 23.09.2026).
               AND NOT EXISTS (
                   SELECT 1 FROM cabinet_publisher cp JOIN cabinet cab ON cab.id = cp.cabinet_id
                    WHERE cp.publisher_id = q.publisher_id AND cab.state = 'приостановлен')
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
              f"доставлено событий {stats['sent']}, не доставлено {stats['failed']}")
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
    }


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
