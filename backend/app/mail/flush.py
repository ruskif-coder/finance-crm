# -*- coding: utf-8 -*-
"""Досылка отложенных писем: у кого настал час — тот уходит.

Письма площадкам, сочинённые в тихие часы (21:00–09:00 по времени площадки), лежат в
журнале со статусом `queued` и своим `send_after`. Эта задача их выпускает.

Задача ОТДЕЛЬНАЯ от `notify.dispatch`, хотя делает похожее: тот разгребает очередь
уведомлений СОТРУДНИКАМ (`notification_deliveries`), эта — очередь писем. Слить их
значило бы завести в коде, адресующем сотрудников, ветку про внешний контур.

    docker exec finance_backend python -m app.mail.flush [--dry-run]

Крон: раз в час. Точность до часа здесь достаточна — письмо, обещанное к девяти утра,
уйдёт в интервале 09:00–09:59, и это ровно то, чего ждёт получатель.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from app.database import SessionLocal
from app.ext_lock import MAIL_FLUSH, only_one
from app.mail import client as mail
from app.mail.models import MailLog
from app.mail.send import _failed
import app.model_registry  # noqa: F401 — крон отдельным процессом: все таблицы для внешних ключей

log = logging.getLogger("finance.mail.flush")


class _Busy(RuntimeError):
    pass


def flush(dry_run: bool = False, limit: int = 500) -> dict:
    """Отправить всё, чей час настал. Возвращает счётчики.

    Один прогон за раз (аудит 23.09.2026, 5.L4): крон и ручной запуск, наложившись,
    брали одни и те же строки, и письмо уходило дважды. Второй прогон ничего не шлёт.
    """
    try:
        with only_one(MAIL_FLUSH, 1, _Busy, "Досылка писем"):
            return _flush(dry_run, limit)
    except _Busy:
        print("досылка: предыдущий прогон ещё идёт — этот пропускаю")
        return {"due": 0, "sent": 0, "failed": 0, "skipped": 0, "busy": True}


def _still_wanted(db, email: str, publisher_id=None) -> bool:
    """Жив ли ещё получатель уведомлений площадке — тем же отбором, что
    `notify.outward.send._recipients`. Площадка известна (строки с 02.10.2026) — ровно её
    контакт: тот же адрес бывает живым контактом другой площадки; старые строки — по адресу."""
    from sqlalchemy import text
    return bool(db.execute(text("""
        SELECT 1 FROM sales_publisher_contacts c
         WHERE lower(c.email) = lower(:e) AND c.notify
           AND (CAST(:p AS integer) IS NULL OR c.publisher_id = :p)
           AND EXISTS (SELECT 1 FROM sales_publishers sp
                        WHERE sp.id = c.publisher_id AND sp.status <> 'АРХИВ')
           AND NOT EXISTS (
               SELECT 1 FROM cabinet_publisher cp JOIN cabinet cab ON cab.id = cp.cabinet_id
                WHERE cp.publisher_id = c.publisher_id AND cab.state = 'приостановлен')
         LIMIT 1"""), {"e": email, "p": publisher_id}).first())


def _flush(dry_run: bool, limit: int) -> dict:
    """Каждое письмо считается отдельно: отказ по одному не отменяет остальных — то же
    правило, что в пакетной отправке, и по той же причине."""
    db = SessionLocal()
    stats = {"due": 0, "sent": 0, "failed": 0, "skipped": 0}
    try:
        if not mail.configured():
            print("почта не настроена — досылать некуда")
            return stats
        now = datetime.utcnow()
        rows = (db.query(MailLog)
                .filter(MailLog.status == "queued",
                        MailLog.send_after.isnot(None),
                        MailLog.send_after <= now)
                .order_by(MailLog.send_after, MailLog.id).limit(limit).all())
        stats["due"] = len(rows)
        for row in rows:
            if dry_run:
                print(f"  (сухой прогон) {row.to_email} ← {row.subject[:60]}")
                stats["skipped"] += 1
                continue
            if row.kind == "pub_notify" and not _still_wanted(db, row.to_email, row.publisher_id):
                # Отложено на тихие часы, а за это время контакт снял отметку, удалён или
                # кабинет приостановлен — то же правило, что при постановке (аудит
                # 01.10.2026, С-6). Письмо не уходит; в журнале остаётся причина.
                row.status, row.error = "suppressed", "получатель больше не принимает уведомления"
                stats["skipped"] += 1
                db.commit()
                continue
            row.attempts += 1
            try:
                # Разметка берётся ИЗ ЖУРНАЛА, а не собирается заново: собрать её
                # нечем — тона, тега, фактов и контекста здесь нет. До 14.09.2026 этой
                # колонки не было, и письмо площадке, попавшее в тихие часы, уходило
                # голым текстом: днём то же самое письмо приходило свёрстанным, вечером
                # — нет. Молча, со статусом `sent`.
                mid = mail.send(to=row.to_email, subject=row.subject, body=row.body,
                                html=row.html, to_name=row.to_name,
                                reply_to=row.reply_to)
                row.status, row.message_id, row.sent_at = "sent", mid, datetime.utcnow()
                row.error = None
                stats["sent"] += 1
            except Exception as e:                          # noqa: BLE001
                _failed(row, e)
                stats["failed"] += 1
                log.warning("Досылка не удалась (%s): %s", row.to_email, e)
            db.commit()
        print(f"Досылка: к отправке {stats['due']}, ушло {stats['sent']}, "
              f"не ушло {stats['failed']}"
              + (", сухой прогон" if dry_run else ""))
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    flush(dry_run="--dry-run" in sys.argv)
