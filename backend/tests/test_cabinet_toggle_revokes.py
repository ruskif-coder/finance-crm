# -*- coding: utf-8 -*-
"""Отключение и включение учётки кабинета отзывают выданные входы (аудит 2.6.76, п. 1.6; сделано 22.10.2026): растёт
`cabinet_account.token_epoch`, а он входит в отпечаток токена кабинета. Всё в откатываемой транзакции."""
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.cabinet.models import CabinetAccount
from app.database import SessionLocal
from app.routers import cabinets as CB


@pytest.fixture
def acc(monkeypatch):
    db = SessionLocal()
    monkeypatch.setattr(db, "commit", db.flush)
    monkeypatch.setattr(CB, "log_action", lambda *a, **k: None)
    monkeypatch.setattr(CB.journal, "write", lambda *a, **k: None)
    a = db.query(CabinetAccount).order_by(CabinetAccount.id).first()
    if a is None:
        db.close()
        pytest.skip("на стенде нет учёток кабинета")
    try:
        yield db, a
    finally:
        db.rollback()
        db.close()


def test_toggle_bumps_epoch_other_edits_do_not(acc):
    db, a = acc
    was, active = a.token_epoch or 0, bool(a.is_active)
    user = SimpleNamespace(id=None, name="тест")
    CB.update_account(a.id, CB.AccountPatch(can_approve=not a.can_approve), db, user)
    assert (a.token_epoch or 0) == was                      # смена уровня входы не отзывает
    CB.update_account(a.id, CB.AccountPatch(is_active=not active), db, user)
    CB.update_account(a.id, CB.AccountPatch(is_active=active), db, user)
    assert a.token_epoch == was + 2
