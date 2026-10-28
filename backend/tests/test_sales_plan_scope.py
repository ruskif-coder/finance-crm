# -*- coding: utf-8 -*-
"""Права «Плана продаж» в ячейке (ревью 27.10.2026, v2.7.0..): пользователь «свои» видит общую цель, но сделки — только свои.
Поломка: в общем разрезе `cell()` отдавал сделки всей компании с суммами, продавцами и клиентами."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.sales import plan


def _deal(i, rep):
    return SimpleNamespace(id=i, code=f"C{i}", title="т", stage="s", month=10, amount=100.0, rep=f"rep{rep}", service="у",
                           advertiser="А", brand=None, sales_rep_id=rep, service_id=1, layer="фактические", light=None,
                           stage_key="archive")


def test_own_scope_sees_only_own_deals_in_common_row(monkeypatch):
    monkeypatch.setattr(plan, "deals_of", lambda db, year: [_deal(1, 7), _deal(2, 8)])
    monkeypatch.setattr(plan, "history", lambda *a, **k: [])
    got = plan.cell(None, 2026, 10, 10, "общий", 0, own=[7])
    assert [d["id"] for d in got["deals"]] == [1]
    assert [d["id"] for d in plan.cell(None, 2026, 10, 10, "общий", 0, own=None)["deals"]] == [1, 2]
