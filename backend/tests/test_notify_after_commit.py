# -*- coding: utf-8 -*-
"""Письма и Telegram — ПОСЛЕ commit действия (аудит v2.6.0→v2.7.0, D1; 21.10.2026).

До правки `emit` слал синхронно внутри транзакции, иногда под `FOR UPDATE` на пакете: SMTP до 30 с держал строку
заблокированной, а откат действия после отправки оставлял письмо о том, чего не было («Вашу сделку добавили в пакет
M-00xx», которого нет). Теперь `emit` пишет строку журнала «в очереди», а отправка идёт после commit — тем же путём,
что досылка (`dispatch._one`: тихие часы, неактивные, протухшие). Откатилось действие — откатилась и строка."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.notify import bus, channels
from app.notify.models import NotificationDelivery


def _uid(db):
    return db.execute(text("SELECT id FROM users WHERE is_active = 1 ORDER BY id LIMIT 1")).scalar()


def test_nothing_is_sent_inside_the_transaction_and_rollback_sends_nothing(monkeypatch):
    from app.database import SessionLocal
    sent = []
    monkeypatch.setattr(channels, "deliver_tg", lambda *a, **k: sent.append("tg") or "sent|")
    monkeypatch.setattr(channels, "deliver_mail", lambda *a, **k: sent.append("mail") or "sent|")
    monkeypatch.setattr(bus, "_channels_for", lambda db, uid, ev: ["tg", "mail"])
    db = SessionLocal()
    try:
        uid = _uid(db)
        bus.emit(db, "act_missing", title="проверка", body="тело", user_ids=[uid], entity_type="test", entity_id=-1)
        rows = db.query(NotificationDelivery).filter_by(entity_type="test", entity_id=-1).all()
        assert sent == [], "отправка ушла до commit действия"
        assert {r.channel for r in rows} == {"tg", "mail"}
        assert all(r.status == "queued" and r.suppress_reason == bus.PENDING for r in rows)
    finally:
        db.rollback()
        db.close()
    assert sent == [], "после отката действия письмо всё равно ушло"


def test_after_commit_sends_through_the_dispatch_path(monkeypatch):
    """Хук после commit берёт строки и отдаёт их `dispatch._one` — один путь отправки на живую доставку и досылку."""
    from app.notify import dispatch
    seen = []

    class _Row:
        def __init__(self, i):
            self.id, self.user_id, self.status, self.suppress_reason = i, 7, "queued", bus.PENDING

    rows = [_Row(1), _Row(2)]

    class _Q:
        def filter(self, *a):
            return self

        def with_for_update(self, **k):
            return self

        def all(self):
            return rows

    class _S:
        def query(self, *a):
            return _Q()

        def commit(self):
            seen.append("commit")

        def rollback(self):
            pass

        def close(self):
            pass

        def execute(self, *a, **k):
            return type("R", (), {"all": lambda self: [(7,)]})()

    monkeypatch.setattr(dispatch, "_one", lambda db, r, now, dry, stats, active: (setattr(r, "status", "sent"), seen.append(r.id)))
    bus._send_after_commit([1, 2], session_factory=_S)
    assert seen == [1, "commit", 2, "commit"]


def test_dispatch_leaves_fresh_pending_rows_to_the_hook():
    """Досылка не берёт строку, которую прямо сейчас отправляет хук после commit, — иначе письмо ушло бы дважды.
    Старую «ждущую» (процесс упал между commit и отправкой) — берёт: ничего не теряется."""
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from app.notify import dispatch
    now = datetime(2026, 10, 21, 12, 0)
    fresh = SimpleNamespace(suppress_reason=bus.PENDING, created_at=now - timedelta(minutes=2))
    stale = SimpleNamespace(suppress_reason=bus.PENDING, created_at=now - timedelta(minutes=30))
    quiet = SimpleNamespace(suppress_reason="quiet_hours", created_at=now - timedelta(minutes=1))
    assert not dispatch.due(fresh, now) and dispatch.due(stale, now) and dispatch.due(quiet, now)


def test_savepoint_is_not_the_commit(monkeypatch):
    """after_commit в SQLAlchemy срабатывает и на выходе из savepoint (ревью 22.10.2026): хук не должен отправлять
    и забывать строки до настоящего commit — иначе новая сессия их не видит, и письмо ждёт досылки до часа."""
    from app.database import SessionLocal
    sent = []
    monkeypatch.setattr(bus, "_channels_for", lambda db, uid, ev: ["tg"])
    monkeypatch.setattr(bus, "_send_after_commit", lambda ids, session_factory=None: sent.append(list(ids)))
    db = SessionLocal()
    try:
        uid = _uid(db)
        bus.emit(db, "act_missing", title="проверка", user_ids=[uid], entity_type="test", entity_id=-2)
        with db.begin_nested():
            db.execute(text("SELECT 1"))
        assert sent == [], "хук сработал на savepoint"
        assert db.info.get(bus._PENDING_KEY), "строки забыты на savepoint"
        with pytest.raises(ZeroDivisionError):
            with db.begin_nested():
                raise ZeroDivisionError
        assert db.info.get(bus._PENDING_KEY), "откат savepoint стёр чужие строки"
    finally:
        db.rollback()
        db.close()
