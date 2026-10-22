# -*- coding: utf-8 -*-
"""Поиск по мастер-сделкам, УПД и счетам из 1С (21.10.2026): DTO как у всех, видимость — областью реестра пакетов."""
from types import SimpleNamespace

from app.search import master as MT
from app.search import engine


def test_types_are_gated_by_master_registry_right():
    for t in ("master_deal", "upd", "invoice"):
        assert engine.SEARCHERS[t][0] == "master_deals"
    assert "upd" not in engine.allowed_types({"sales_registry": {"view": True}})
    assert {"master_deal", "upd", "invoice"} <= set(engine.allowed_types({"master_deals": {"view": True}}))


def test_no_scope_row_means_nothing(monkeypatch):
    from fastapi import HTTPException

    def deny(db, user):
        raise HTTPException(403, "нет строки права")
    monkeypatch.setattr(MT.SC, "own_reps", deny)
    assert MT._visible(None, {"user": None}, [SimpleNamespace(id=1)]) == set()


def test_own_scope_filters_packages(monkeypatch):
    monkeypatch.setattr(MT.SC, "own_reps", lambda db, user: [7])
    monkeypatch.setattr(MT.SC, "in_scope", lambda db, m, own: m.id == 2)
    assert MT._visible(None, {"user": None}, [SimpleNamespace(id=1), SimpleNamespace(id=2)]) == {2}


def test_real_package_found_by_code_and_upd_number(db):
    from app.master_deal.models import MasterDeal, MasterDealUpd
    m = db.query(MasterDeal).join(MasterDealUpd, MasterDealUpd.master_deal_id == MasterDeal.id) \
        .filter(MasterDealUpd.onec_upd_no.isnot(None)).first()
    if m is None:
        import pytest
        pytest.skip("на стенде нет пакета с УПД из 1С")
    admin = SimpleNamespace(id=None)
    ctx = {"user": admin, "master_own": ("ok", None)}
    rows = MT.master_deals(db, m.code, 5, 0, ctx)
    assert rows and rows[0]["title"] == m.code and rows[0]["href"] == f"/accounts/master/{m.code}"
    assert set(rows[0]) == {"id", "title", "subtitle", "href", "archived"}
    k = db.query(MasterDealUpd).filter_by(master_deal_id=m.id).filter(MasterDealUpd.onec_upd_no.isnot(None)).first()
    found = MT.upds(db, k.onec_upd_no, 5, 0, ctx)
    assert any(r["title"].startswith(f"УПД № {k.onec_upd_no}") and m.code in r["subtitle"] for r in found)
    inv = MT.invoices(db, k.onec_invoice_no, 5, 0, ctx)
    assert any(r["title"].startswith(f"Счёт № {k.onec_invoice_no}") for r in inv)


def test_code_typed_in_russian_or_without_dash():
    assert MT._code_form("м-1172") == "M-1172"
    assert MT._code_form("M1172") == "M-1172"
    assert MT._code_form("Альфарм") == "Альфарм"
