# -*- coding: utf-8 -*-
"""Сверка и приоритезация площадке (прод 06.11.2026): отправитель звал `notify_publisher` внутри `db.begin_nested()`, а тот
фиксирует базу сам (`_to_panel` → `db.commit()`). Следующая же команда в закрытом savepoint падала, исключение глоталось —
с 02.11 площадкам доходила только строка в ленте кабинета, без письма и бота. Прибор: отправитель, который коммитит, —
и уведомление всё равно отправлено. Записей на стенд нет: отправитель подменён и пишет только SELECT."""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.notify import outward
from app.notify import prio as P
from app.notify import recon as N


@pytest.fixture
def db_pub():
    from app.database import SessionLocal
    db = SessionLocal()
    pid = db.execute(text("SELECT id FROM sales_publishers WHERE status <> 'АРХИВ' ORDER BY id LIMIT 1")).scalar()
    if pid is None:
        pytest.skip("на стенде нет площадки")
    try:
        yield db, pid
    finally:
        db.rollback()
        db.close()


def _committing_sender(calls):
    def send(db, kind, publisher_id, **kw):
        db.execute(text("SELECT 1"))
        db.flush()
        db.commit()                        # как настоящий: лента кабинета фиксируется внутри
        db.execute(text("SELECT 2"))       # и дальше идут бот и почта
        calls.append(kind)
        return {"status": "sent"}
    return send


def test_recon_notice_survives_sender_commit(db_pub, monkeypatch):
    db, pid = db_pub
    calls = []
    monkeypatch.setattr(outward, "notify_publisher", _committing_sender(calls))
    req = SimpleNamespace(id=1, publisher_id=pid, period="2026-10", due_at=date(2026, 11, 10), recon=None)
    assert N.to_site(db, req, "новая")["status"] == "sent" and calls == ["сверка"]


def test_prio_notice_survives_sender_commit(db_pub, monkeypatch):
    db, pid = db_pub
    calls = []
    monkeypatch.setattr(outward, "notify_publisher", _committing_sender(calls))
    from app.launch_prep import erid_service
    monkeypatch.setattr(erid_service, "_deal_brand_name", lambda db, deal: "Бренд")
    monkeypatch.setattr(erid_service, "deal_period_text", lambda deal: "11.2026")
    out = P._outward(db, "запрос приоритезации", SimpleNamespace(), SimpleNamespace(id=1, publisher_id=pid), "Запрос", "текст")
    assert out["status"] == "sent" and calls == ["запрос приоритезации"]
