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


def test_deal_code_finds_its_master_deal_too(db):
    """Владелец 12.11.2026: «в поиске по сайту, чтобы тоже показывал в том числе мастер-сделку» — по коду исходной сделки."""
    from sqlalchemy import text
    from app.search import classify
    row = db.execute(text("""SELECT d.code, m.code FROM master_deal_items i JOIN sales_deals d ON d.id = i.deal_id
                              JOIN master_deals m ON m.id = i.master_deal_id WHERE d.code IS NOT NULL LIMIT 1""")).first()
    if row is None:
        import pytest
        pytest.skip("на стенде нет сделок в пакетах")
    assert "master_deal" in classify.classify(row[0])["types"]
    ctx = {"user": SimpleNamespace(id=None), "master_own": ("ok", None)}
    rows = MT.master_deals(db, row[0], 5, 0, ctx)
    assert rows and rows[0]["title"] == row[1] and row[0] in rows[0]["subtitle"]


def test_registry_rows_carry_deal_codes_for_search():
    """Поиск реестра мастер-сделок по коду исходной сделки (12.11.2026): строка реестра несёт коды своих сделок."""
    from app.database import SessionLocal
    from app.master_deal import registry as RG
    db = SessionLocal()
    try:
        rows = RG.rows(db, SimpleNamespace(id=None, role=SimpleNamespace(key="admin", is_master=True)))
    finally:
        db.close()
    if not rows:
        import pytest
        pytest.skip("на стенде нет мастер-сделок")
    assert all("deal_codes" in r for r in rows) and any(r["deal_codes"] for r in rows)


def test_partial_query_does_not_reveal_a_deal_code(db):
    """Ревью 12.11.2026: по куску текста пакет найдётся, но код сделки в подписи — только при точном совпадении."""
    from sqlalchemy import text
    row = db.execute(text("""SELECT d.code FROM master_deal_items i JOIN sales_deals d ON d.id = i.deal_id
                              WHERE d.code IS NOT NULL LIMIT 1""")).first()
    if row is None:
        import pytest
        pytest.skip("на стенде нет сделок в пакетах")
    ctx = {"user": SimpleNamespace(id=None), "master_own": ("ok", None)}
    rows = MT.master_deals(db, row[0][:4], 50, 0, ctx)
    assert rows and not any(f"сделка {row[0]}" in r["subtitle"] for r in rows)
