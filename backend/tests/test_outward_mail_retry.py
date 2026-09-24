# -*- coding: utf-8 -*-
"""Письмо площадке: временный сбой не делает его окончательным, прогоны не двоят
(аудит 23.09.2026, 5.L3 и 5.L4).

5.L3. Статус `failed` был окончательным: почтовый сервер на минуту недоступен — письмо
не уходит никогда, и досылка его не берёт. А ручной повтор (`retry`) терял вёрстку:
`html` не передавался, и площадка получала голый текст.

5.L4. Досылка и дайджест площадкам выбирали строки без блокировки: наложились два
прогона (крон + ручной запуск) — каждое письмо ушло дважды.

Временным считается только то, после чего письмо точно НЕ ушло: сервер недоступен или
ответил 4xx. Обрыв посреди отправки временным не считается — письмо могло дойти, и
повтор дал бы второе.
"""
from datetime import datetime

import pytest
from sqlalchemy import text

import app.models  # noqa: F401
from app.database import SessionLocal, engine
from app.mail import client as mail
from app.mail import flush as mflush
from app.mail import send as msend
from app.mail.models import MailLog

TO = "retry-test@example.invalid"


@pytest.fixture
def db(monkeypatch):
    s = SessionLocal()
    monkeypatch.setattr(mail, "configured", lambda: True)
    # Настройки ящика — подставные: на стенде почты нет, а до транспорта письмо
    # доходит только через проверку настроек.
    monkeypatch.setattr(mail, "config", lambda: mail.MailConfig(
        host="smtp.example.invalid", port=465, user="", password="",
        sender="noreply@example.invalid", sender_name="Тест", mode="ssl"))

    def purge():
        s.rollback()
        s.query(MailLog).filter(MailLog.to_email == TO).delete()
        s.commit()
    purge()
    yield s
    purge()
    s.close()


def _temporary(msg):
    raise mail.MailTemporary("Почтовый сервер недоступен: ConnectionRefusedError")


def _permanent(msg):
    raise mail.MailError("Письмо не принято: 550 no such user")


def test_a_temporary_failure_is_queued_for_retry(db):
    row = msend.send_and_log(db, to=TO, subject="т", body="т", kind="test",
                             html="<b>т</b>", transport=_temporary)
    assert row.status == "queued" and row.send_after is not None, (
        "временный сбой записан окончательным — письмо не уйдёт никогда")


def test_a_permanent_failure_stays_failed(db):
    row = msend.send_and_log(db, to=TO, subject="т", body="т", kind="test",
                             transport=_permanent)
    assert row.status == "failed"


def test_retries_are_limited(db):
    """Последняя разрешённая попытка, снова временный сбой — письмо «не ушло», а не в
    очередь навечно. Начинаем с очереди: до правки такой строки не бывало вовсе."""
    row = msend.send_and_log(db, to=TO, subject="т", body="т", kind="test",
                             transport=_temporary)
    assert row.status == "queued"
    row.attempts = msend.MAX_ATTEMPTS - 1
    db.commit()
    again = msend.retry(db, row.id, transport=_temporary)
    assert again.status == "failed"


def test_manual_retry_keeps_the_layout(db):
    row = msend.send_and_log(db, to=TO, subject="т", body="т", kind="test",
                             html="<b>вёрстка</b>", transport=_permanent)
    seen = {}

    def ok(msg):
        seen["html"] = any(p.get_content_type() == "text/html" for p in msg.walk())

    msend.retry(db, row.id, transport=ok)
    assert seen["html"], "повтор отправил письмо без вёрстки"


def test_overlapping_flush_runs_do_not_send_twice(db, monkeypatch):
    from app.ext_lock import MAIL_FLUSH

    db.add(MailLog(to_email=TO, subject="т", body="т", kind="test", status="queued",
                   send_after=datetime(2000, 1, 1), attempts=0))
    db.commit()
    monkeypatch.setattr(mail, "send", lambda **kw: pytest.fail("второй прогон отправил"))
    holder = engine.connect()
    holder.execute(text("SELECT pg_advisory_lock(:a, 1)"), {"a": MAIL_FLUSH})
    try:
        out = mflush.flush()
        assert out.get("busy")
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:a, 1)"), {"a": MAIL_FLUSH})
        holder.close()
