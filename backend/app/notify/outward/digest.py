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

`mail/render.py::digest_html` — шапка со счётчиками, карточки по тяжести тона — написан с
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
import os
import sys
from collections import defaultdict

from sqlalchemy import text

from app.database import SessionLocal
from app.mail import client as mail
from app.mail import render
from app.mail.send import send_and_log

log = logging.getLogger("finance.cabinet.digest")

KIND_DIGEST = "pub_digest"      # вид письма в журнале почты
BATCH = 500                     # столько строк очереди разгребаем за прогон


def run(dry_run: bool = False) -> dict:
    """Разослать пачки, чей час настал. Возвращает счётчики.

    Каждый адрес считается отдельно: отказ по одному не отменяет остальных — то же
    правило, что в пакетной отправке гейта и в досылке, и по той же причине.
    """
    db = SessionLocal()
    stats = {"due": 0, "letters": 0, "sent": 0, "failed": 0}
    try:
        if not mail.configured():
            print("почта не настроена — дайджест собирать некуда")
            return stats

        rows = db.execute(text("""
            SELECT id, publisher_id, contact_id, email, to_name, kind, title, body,
                   context, link_abs, facts, tone, tag, created_at
              FROM cabinet_digest_queue
             WHERE sent_at IS NULL AND due_at <= now()
             ORDER BY due_at, id
             LIMIT :n"""), {"n": BATCH}).fetchall()
        stats["due"] = len(rows)
        if not rows:
            print("к отправке ничего нет")
            return stats

        by_addr = defaultdict(list)
        for r in rows:
            by_addr[r.email].append(r)

        brand = (os.getenv("MAIL_FROM_NAME") or "SIMB-AD").strip()
        for email, items in by_addr.items():
            to_name = next((r.to_name for r in items if r.to_name), "")
            cards = [{
                "title": r.title, "body": r.body, "link_abs": r.link_abs,
                "tone": r.tone or "info", "tag": r.tag or "",
                "context": r.context,
                # Час события, а не час письма: в пачке из шести карточек «когда это
                # случилось» — половина смысла.
                "when": r.created_at.strftime("%H:%M") if r.created_at else "",
                "facts": [tuple(f) for f in (r.facts or [])],
                "action": "Открыть кабинет",
            } for r in items]

            html = render.digest_html(items=cards, to_name=to_name, brand=brand,
                                      logo_url=render.abs_url(render.LOGO_PATH))
            # Тема НАЗЫВАЕТ ЧИСЛО: «уведомления» без числа неотличимо от одного события,
            # и письмо открывают, чтобы узнать, сколько их.
            subject = f"{len(items)} {_plural(len(items))} за сутки"
            body = "\n\n".join(
                render.text_body(r.title if not r.context else f"{r.title}\n{r.context}",
                                 r.body, r.link_abs, [tuple(f) for f in (r.facts or [])])
                for r in items)

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
