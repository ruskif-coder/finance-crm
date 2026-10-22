# -*- coding: utf-8 -*-
"""Время фактической отправки в журнале (`notification_deliveries.sent_at`, владелец 21.10.2026).

`created_at` — время события: письмо, отложенное тихими часами до утра, выглядело в журнале так же, как ушедшее ночью,
и жалобу «пришло ночью» было не проверить. Ставится там, где строка становится «отправлено»."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.notify import dispatch
from app.notify.models import NotificationDelivery


def test_model_has_sent_at():
    assert "sent_at" in NotificationDelivery.__table__.columns


def test_dispatch_stamps_the_moment_of_sending(monkeypatch):
    from app.notify import channels, registry
    ev = registry.get("act_missing")
    r = SimpleNamespace(user_id=1, created_at=datetime.utcnow() - timedelta(hours=3), event_key=ev.key, channel="mail",
                        title="t", body="b", link=None, facts=[], code=None, status="queued", suppress_reason="quiet_hours",
                        sent_at=None, entity_type=None, entity_id=None, error=None)
    monkeypatch.setattr(channels, "deliver_mail", lambda *a, **k: "sent|")

    class _Q:
        def filter(self, *a):
            return self

        def first(self):
            return None

    class _Db:
        def query(self, *a):
            return _Q()
    stats = {"sent": 0, "skipped": 0, "expired": 0, "failed": 0}
    dispatch._one(_Db(), r, datetime.utcnow(), False, stats, {1})
    assert r.status == "sent" and r.sent_at is not None and r.sent_at > r.created_at
