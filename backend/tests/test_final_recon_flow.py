# -*- coding: utf-8 -*-
"""Цикл услуги (владелец 14.10.2026): «контур аккаунта» — сборка только по доходному договору; пусто у услуги — полный цикл."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.final_recon import flow
from app.sales import stage_checks as SC


def test_scope_by_closing_flow_and_empty_means_full_cycle():
    acc = SimpleNamespace(service_id=24, closing_flow=flow.ACCOUNT)
    full = SimpleNamespace(service_id=28, closing_flow=flow.FULL)
    assert SC.scope_matches({"closing_flow": flow.ACCOUNT}, acc)
    assert not SC.scope_matches({"closing_flow": flow.ACCOUNT}, full)
    assert flow.of_deal(None, SimpleNamespace(service_id=None)) == flow.FULL          # нет услуги — полный цикл
    assert "closing_flow" in SC.SCOPE_KEYS


def test_account_finished_is_registered():
    """«Сделка завершена аккаунтом» — пара к «РК завершена трафиком» для контура аккаунта (стадии ДО)."""
    assert "account_finished" in SC.REGISTRY and "account_finished" in SC.PLACES


def test_account_buttons_only_for_account_flow_and_right_stage(monkeypatch):
    import pytest
    from app.final_recon import launch as L
    stages = {1: SimpleNamespace(id=1, name="Готовятся к старту"), 2: SimpleNamespace(id=2, name="В размещении"),
              3: SimpleNamespace(id=3, name="Итоговая сверка")}
    monkeypatch.setattr(L, "Catalog", lambda db: SimpleNamespace(by_id=stages))
    moved = []
    monkeypatch.setattr(L.stage_move, "plan_move", lambda db, d, t, c: SimpleNamespace(target=t))
    monkeypatch.setattr(L.stage_move, "may_move", lambda p: True)
    monkeypatch.setattr(L.stage_move, "apply_move", lambda db, d, t, u, **k: moved.append(t.name) or {"moved": True})
    acc = SimpleNamespace(id=1, our_stage_id=1, service_id=24, closing_flow=flow.ACCOUNT)
    assert L.available(None, acc) == "launch"
    assert L.run(None, acc, "launch", None)["stage"] == "В размещении" and moved == ["В размещении"]
    with pytest.raises(L.LaunchError):
        L.run(None, acc, "finish", None)                                   # не та стадия
    full = SimpleNamespace(id=2, our_stage_id=1, service_id=28, closing_flow=flow.FULL)
    assert L.available(None, full) is None
    with pytest.raises(L.LaunchError):
        L.run(None, full, "launch", None)                                  # полный цикл — у трафика
