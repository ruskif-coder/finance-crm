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
