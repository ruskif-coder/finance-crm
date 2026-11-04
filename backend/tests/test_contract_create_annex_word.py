# -*- coding: utf-8 -*-
"""Новый договор сохраняет «вид ДС» (ревью 05.11.2026): `create_contract` его не писал — выбрали «ДС», а документ печатался
«Приложением». Значение проходит ту же проверку, что правка договора (`annex_tpl/doc_kind.normalize_word`)."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.models import Counterparty
from app.routers import contracts as R


@pytest.fixture
def db(monkeypatch):
    s = SessionLocal()
    monkeypatch.setattr(s, "commit", s.flush)
    monkeypatch.setattr(R, "log_action", lambda *a, **k: None)
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_new_contract_keeps_its_annex_word(db):
    cp = Counterparty(name="тест вида ДС договора", inn="7700000002")
    db.add(cp)
    db.flush()
    user = SimpleNamespace(id=None, name="тест", role=SimpleNamespace(key="admin"), role_id=None)
    out = R.create_contract(R.ContractCreate(counterparty_id=cp.id, contract_number="ВД-1", annex_word="ДС"), db, user)
    assert db.get(R.Contract, out["id"]).annex_word == "дс"
    with pytest.raises(HTTPException):
        R.create_contract(R.ContractCreate(counterparty_id=cp.id, contract_number="ВД-2", annex_word="соглашение"), db, user)
