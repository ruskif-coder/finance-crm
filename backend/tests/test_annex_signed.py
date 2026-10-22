# -*- coding: utf-8 -*-
"""Подписан ли ДС (app/sales/annex_signed.py, владелец 16.10.2026): одна функция с источниками — ЭДО (место под него), файл
подписанного ДС у сделки, иначе «не подписан»; расхождение источников — тревога. Транзакция откатывается."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.sales import annex_signed as AS


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _annex_with_deal(db):
    row = db.execute(text("""SELECT al.annex_id, al.deal_id FROM sales_deal_annex_allocation al
        WHERE NOT EXISTS (SELECT 1 FROM sales_deal_files f WHERE f.deal_id = al.deal_id AND f.kind = 'ds') LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет ДС со сделкой без файла ДС")
    return SimpleNamespace(id=row[0]), row[1]


def test_no_data_is_not_signed(db):
    a, _ = _annex_with_deal(db)
    st = AS.signed_state(db, a)
    assert st == {"signed": False, "source": None, "source_label": "нет данных", "at": None, "conflict": False}


def test_signed_file_on_deal_makes_it_signed(db):
    a, deal_id = _annex_with_deal(db)
    db.execute(text("INSERT INTO sales_deal_files (deal_id, kind, filename, path) VALUES (:d, 'ds', 'ДС подписан.pdf', '/tmp/x')"), {"d": deal_id})
    st = AS.signed_state(db, a)
    assert st["signed"] and st["source"] == "file"


def test_edo_wins_and_conflict_is_flagged(db, monkeypatch):
    a, deal_id = _annex_with_deal(db)
    db.execute(text("INSERT INTO sales_deal_files (deal_id, kind, filename, path) VALUES (:d, 'ds', 'x.pdf', '/tmp/x')"), {"d": deal_id})
    monkeypatch.setattr(AS, "_from_edo", lambda db, a: {"signed": False, "at": None})
    st = AS.signed_state(db, a)
    assert st["source"] == "edo" and st["signed"] is False and st["conflict"] is True
