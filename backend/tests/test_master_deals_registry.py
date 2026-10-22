# -*- coding: utf-8 -*-
"""Реестр мастер-сделок в «Финансах» и право `master_deals` (владелец 19.10.2026: «нет / просмотр / редактирование»)."""
import inspect

import pytest

import app.model_registry  # noqa: F401
from app.permissions import SECTIONS
from app.master_deal import registry as RG
from app.master_deal import scope as SC
from app.routers import master_deals as R


def test_section_is_finance_with_view_and_edit():
    s = next(x for x in SECTIONS if x["key"] == "master_deals")
    assert s["group"] == "Финансы" and s["actions"] == ["view", "edit"]


def test_every_route_is_gated_by_master_deals_permission():
    """Читающие ручки — `master_deals` view, пишущие — edit; право реестра сделок пакет больше не открывает."""
    src = inspect.getsource(R)
    assert 'require_permission("master_deals", "view")' in src and 'require_permission("master_deals", "edit")' in src
    for route in R.router.routes:
        calls = {d.call for d in route.dependant.dependencies}
        writes = bool(route.methods & {"PUT", "POST", "DELETE"}) and not route.path.endswith("/preview")
        want = R.MD_EDIT if writes else R.MD_VIEW
        if route.path.endswith("/efficiency"):        # своё право — «Эффективность мастер-сделок»
            continue
        assert want in calls, f"{route.methods} {route.path}: нет права master_deals {'edit' if writes else 'view'}"


def test_registry_lists_only_packages_in_scope(monkeypatch):
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    db = SessionLocal()
    try:
        all_codes = {m.code for m in db.query(MasterDeal)}
        if not all_codes:
            pytest.skip("на стенде нет мастер-сделок")
        monkeypatch.setattr(SC, "own_reps", lambda db, user: None)
        rows = RG.rows(db, object())
        assert {r["code"] for r in rows} == all_codes
        r = rows[0]
        assert {"code", "status", "period", "contract", "counterparty", "deals", "net", "gross", "ds", "built_by", "advertisers", "brands", "todo"} <= set(r)
        monkeypatch.setattr(SC, "own_reps", lambda db, user: {-1})
        assert RG.rows(db, object()) == [], "роль «свои» без своих сделок видит чужие пакеты"
    finally:
        db.rollback()
        db.close()
