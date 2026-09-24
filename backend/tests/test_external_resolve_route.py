# -*- coding: utf-8 -*-
"""Ручки сверки «исход неизвестен» на дашборде трафика.

Список зависших попыток приходит в том же ответе, что план действия (`external-plan`),
— человек видит их там, где нажимает «DSP» и «ПИКСЕЛЬ WR». Отметка — отдельная ручка
под тем же правом, что сами кнопки, и попадает в журнал действий.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.ad import unknown as U
from app.routers import traffic_dashboard as td


@pytest.fixture
def wired(monkeypatch):
    camp = SimpleNamespace(id=5, deal_id=1)
    logged = []
    monkeypatch.setattr(td, "_campaign_in_scope",
                        lambda db, cid, u: (camp, SimpleNamespace(id=1)))
    monkeypatch.setattr(td, "log_action", lambda *a, **kw: logged.append(a))
    return SimpleNamespace(camp=camp, logged=logged, user=SimpleNamespace(id=1, name="т"))


def test_the_plan_carries_the_hung_attempts(wired, monkeypatch):
    from app.dsp import provision as dp
    from app.weborama import provision as wp
    monkeypatch.setattr(wp, "plan", lambda db, c: {"todo": 0})
    monkeypatch.setattr(wp, "default_landing", lambda db, c: "https://simb-ad.com")
    monkeypatch.setattr(dp, "plan", lambda db, c: {"todo": 0})
    hung = [{"system": "dsp", "ref": "cr1", "what": "креатив", "label": "X-cr1"}]
    monkeypatch.setattr(U, "list_unknown", lambda db, c: hung)
    out = td.external_plan(5, None, wired.user)
    assert out["unknown"] == hung


def test_resolution_is_logged_and_refusal_is_400(wired, monkeypatch):
    monkeypatch.setattr(U, "resolve", lambda db, c, system, ref, **kw: {"found": False})
    td.resolve_external(5, td.ResolveIn(system="dsp", ref="cr1", found=False),
                        None, wired.user)
    assert wired.logged and wired.logged[0][2] == "external_resolve"

    def refuse(*a, **kw):
        raise U.ResolveError("нет такой попытки")
    monkeypatch.setattr(U, "resolve", refuse)
    with pytest.raises(HTTPException) as e:
        td.resolve_external(5, td.ResolveIn(system="dsp", ref="cr1", found=False),
                            None, wired.user)
    assert e.value.status_code == 400 and "нет такой попытки" in e.value.detail
