# -*- coding: utf-8 -*-
"""Отправка письма НАРУЖУ с записью в журнал. Единственный путь для внешних писем.

ПОЧЕМУ ОТДЕЛЬНО ОТ `client.py`. Клиент — транспорт: он умеет положить письмо в SMTP и
ничего не знает про нашу базу. Здесь — правило работы: строка в журнале появляется ДО
отправки, а не после ответа сервера.

Порядок именно такой, и это тот же порядок, что в журналах ОРД, DSP и Weborama:
отправка наружу необратима, а ответ может потеряться по таймауту. Без следа «попытка
была» повтор шлёт площадке второе письмо, и отозвать его нечем. Строка, оставшаяся в
`queued`, читается однозначно: исход неизвестен, разбираться человеку.

ЖУРНАЛ КОММИТИТСЯ СВОЕЙ ТРАНЗАКЦИЕЙ. Вызывающий может откатить свою работу — например
не сохранить запрос ссылки, — но письмо-то уже ушло, и запись о нём обязана пережить
откат вызывающего.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.mail import client as mail
from app.mail.models import MailLog

log = logging.getLogger("finance.mail")

# Временный сбой (сервер недоступен, ответ 4xx) — не приговор: письмо встаёт в очередь
# досылки через полчаса, и так до трёх попыток (аудит 23.09.2026, 5.L3). Досылка
# (`mail.flush`) берёт его по `send_after`, как отложенное на тихие часы.
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=30)


def outcome(row) -> str:
    """Исход письма словом для экрана: sent | retry | queued | failed.

    `retry` — отдельно от `queued` (ревью 23.09.2026): у обоих статус в журнале «в
    очереди», но «ждёт, когда настроят почту» и «сервер был недоступен, уйдёт само через
    полчаса» — разные вещи для человека. Назвать повтор «не ушло» значит заставить его
    отправить текст руками, а досылку — ещё раз.
    """
    if row.status == "queued" and row.error and row.send_after:
        return "retry"
    return row.status


def _failed(row: MailLog, e: Exception) -> None:
    """Записать неудачу: временную — в очередь досылки, прочую — окончательно."""
    row.error = str(e)[:500]
    if isinstance(e, mail.MailTemporary) and row.attempts < MAX_ATTEMPTS:
        row.status, row.send_after = "queued", datetime.utcnow() + RETRY_AFTER
    else:
        row.status = "failed"


def send_and_log(db: Session, *, to: str, subject: str, body: str, kind: str,
                 html: Optional[str] = None, send_after=None,
                 to_name: Optional[str] = None, reply_to: Optional[str] = None,
                 entity_type: Optional[str] = None, entity_id: Optional[int] = None,
                 user_id: Optional[int] = None,
                 transport=None) -> MailLog:
    """Отправить письмо и записать факт. Возвращает строку журнала.

    Исключение НЕ поднимается: вызывающему важнее знать исход, чем ловить ошибку. Статус
    строки и есть ответ — `sent`, `failed` или `queued` (канал не настроен).
    """
    row = MailLog(to_email=(to or "").strip()[:320], to_name=(to_name or None),
                  reply_to=(reply_to or None), subject=subject, body=body, kind=kind,
                  entity_type=entity_type, entity_id=entity_id, user_id=user_id,
                  send_after=send_after, html=html, status="queued", attempts=0)
    db.add(row)
    db.commit()          # СНАЧАЛА след, потом отправка — см. шапку модуля

    if send_after is not None:
        # Тихие часы: строка остаётся `queued` со своим часом, досылка заберёт её сама.
        # Возвращаем её как есть — вызывающий узнаёт из статуса, что письмо не ушло
        # СЕЙЧАС, и не выдаёт отложенное за отправленное.
        return row

    if not mail.configured():
        # Не ошибка, а состояние: уйдёт, когда почту настроят. Попытку не считаем —
        # её не было.
        return row

    row.attempts += 1
    try:
        # Разметка вторым куском: в журнал пишем ТЕКСТ. Он и есть содержание письма,
        # а хранить рядом ещё и разметку значит удвоить таблицу ради того, что никто
        # не читает глазами.
        mid = mail.send(to=row.to_email, subject=subject, body=body, to_name=to_name,
                        reply_to=reply_to, html=html, transport=transport)
        row.status, row.message_id, row.sent_at = "sent", mid, datetime.utcnow()
        row.error = None
    except mail.MailNotConfigured:
        row.status = "queued"
    except Exception as e:                                  # noqa: BLE001
        _failed(row, e)
        log.warning("Письмо не ушло (%s -> %s): %s", kind, row.to_email, e)
    db.commit()
    return row


def retry(db: Session, row_id: int, *, transport=None) -> Optional[MailLog]:
    """Повторить отправку одной строки журнала.

    Повторяем ТОЛЬКО `failed` и `queued`. Уже отправленное не трогаем никогда: у
    получателя появилось бы второе письмо, а у нас — уверенность, что это одно и то же.
    """
    row = db.query(MailLog).filter(MailLog.id == row_id).first()
    if row is None or row.status == "sent":
        return row
    if not mail.configured():
        return row
    row.attempts += 1
    try:
        # С вёрсткой: до 23.09.2026 повтор терял `html`, и площадка получала голый текст.
        mid = mail.send(to=row.to_email, subject=row.subject, body=row.body,
                        html=row.html, to_name=row.to_name, reply_to=row.reply_to,
                        transport=transport)
        row.status, row.message_id, row.sent_at = "sent", mid, datetime.utcnow()
        row.error = None
    except Exception as e:                                  # noqa: BLE001
        _failed(row, e)
    db.commit()
    return row


__all__ = ["send_and_log", "retry", "outcome", "MAX_ATTEMPTS", "RETRY_AFTER"]
