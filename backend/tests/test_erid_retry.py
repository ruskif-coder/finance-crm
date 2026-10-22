# -*- coding: utf-8 -*-
"""ЕРИД: потерянный ответ ОРД — сначала свериться с ОРД, потом повторять; «восстановился» после падения (владелец 15.10.2026)."""
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.launch_prep import erid_auto as EA
from app.ord import submit as S

SET = SimpleNamespace(id=777)


def _patch(monkeypatch, stuck, found=None, boom=False):
    closed = {}
    monkeypatch.setattr(S, "pending", lambda db, k, i, env: stuck)
    monkeypatch.setattr(S, "_finish", lambda db, row, **kw: closed.update(kw))

    def get(path):
        if boom:
            raise RuntimeError("связи нет")
        return [{"id": "c-1", "nativeCustomerId": "set-777", "status": "Registering"}] if found else [{"nativeCustomerId": "set-1"}]
    monkeypatch.setattr(S.client, "get", get)
    return closed


def test_found_in_ord_closes_attempt_with_its_id(monkeypatch):
    closed = _patch(monkeypatch, SimpleNamespace(error="обрыв связи"), found=True)
    assert S.resolve_pending_creative(None, SET, "prod") == "c-1"
    assert closed["ord_id"] == "c-1" and "найден в ОРД" in closed["error"]


def test_absent_in_ord_allows_retry(monkeypatch):
    closed = _patch(monkeypatch, SimpleNamespace(error="таймаут"))
    assert S.resolve_pending_creative(None, SET, "prod") is None
    assert "ord_id" not in closed and "повтор разрешён" in closed["error"]


def test_lookup_failure_keeps_the_block(monkeypatch):
    closed = _patch(monkeypatch, SimpleNamespace(error="таймаут"), boom=True)
    assert S.resolve_pending_creative(None, SET, "prod") is None and closed == {}


def test_no_stuck_attempt_does_nothing(monkeypatch):
    closed = _patch(monkeypatch, None)
    assert S.resolve_pending_creative(None, SET, "prod") is None and closed == {}


@pytest.mark.parametrize("prev,failed,want", [({"failed": ["x"]}, False, True), ({"refresh_failed": 2}, False, True),
                                              ({"failed": []}, False, False), ({"failed": ["x"]}, True, False), (None, False, False)])
def test_recovered_only_after_a_failing_run(prev, failed, want):
    out = {"issue": {"failed": ["e"] if failed else []}, "refresh": {"failed": []}}
    assert EA.should_recover(prev, out) is want
