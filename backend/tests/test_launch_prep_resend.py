# -*- coding: utf-8 -*-
"""Повторная отправка отказанного креатива площадке — только админ (владелец 14.10.2026)."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.audit import require_admin
from app.routers import launch_prep as L


class _Q:
    def __init__(self, obj):
        self.obj = obj

    def filter(self, *a, **k):
        return self

    def first(self):
        return self.obj


def _run(monkeypatch, *, verdict="отказ", withdrawn=None, state="отказ площадки"):
    pair = SimpleNamespace(id=429, set_id=147, target_id=380, sent_at=datetime(2026, 10, 5), withdrawn_at=withdrawn)
    review = SimpleNamespace(verdict=verdict, reason="нет товара", decided_at=datetime(2026, 10, 9, 10, 43), decided_by="Площадка",
                             decided_email="x@y", asked_at=datetime(2026, 10, 5))
    target = SimpleNamespace(id=380, deal_id=2586, publisher_id=15, state=state)
    objs = {L.LaunchPrepPair: pair, L.LaunchPrepReview: review, L.LaunchPrepTarget: target,
            L.LaunchPrepCreativeSet: SimpleNamespace(no=3)}
    logs = []
    monkeypatch.setattr(L, "log_action", lambda db, u, action, et, eid, details: logs.append((action, eid, details)))
    db = SimpleNamespace(query=lambda m: _Q(objs[m]), commit=lambda: None)
    out = L.resend_pair(429, db, SimpleNamespace(id=1))
    return out, pair, review, target, logs


def test_refusal_is_cleared_and_the_old_answer_goes_to_the_log(monkeypatch):
    out, pair, review, target, logs = _run(monkeypatch)
    assert review.verdict is None and review.reason is None and review.decided_at is None
    assert pair.sent_at > datetime(2026, 10, 13) and review.asked_at == pair.sent_at
    assert target.state == "согласование" and out["ok"]
    action, deal_id, details = logs[0]
    assert action == "resend_creative_pair" and deal_id == 2586
    assert "«отказ» 09.10.2026 10:43 UTC" in details and "нет товара" in details and "Креатив № 3" in details


def test_only_a_refused_and_not_withdrawn_pair_is_resent(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _run(monkeypatch, verdict=None)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e2:
        _run(monkeypatch, withdrawn=datetime(2026, 10, 6))
    assert e2.value.status_code == 409


def test_route_is_admin_only():
    route = next(r for r in L.router.routes if getattr(r, "path", "").endswith("/pair/{pair_id}/resend"))
    assert any(d.call is require_admin for d in route.dependant.dependencies)
    with pytest.raises(HTTPException) as e:
        require_admin(SimpleNamespace(role=SimpleNamespace(key="account")))
    assert e.value.status_code == 403
