# -*- coding: utf-8 -*-
"""Банковские счета контрагента: убрать счёт — это удаление, нужно право «удаление» (аудит 2.6.76, п. 1.22; сделано 22.10.2026).
Раньше право проверял только экран, а ручка под «правкой» перезаписывала счета целиком — запросом в обход экрана счёт стирался.
Всё в откатываемой транзакции."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.models import Counterparty, CounterpartyBankAccount
from app.routers import counterparties as CP


@pytest.fixture
def cp_with_accounts(monkeypatch):
    db = SessionLocal()
    monkeypatch.setattr(db, "commit", db.flush)                 # ничего не записать на стенд
    monkeypatch.setattr(CP, "log_action", lambda *a, **k: None)
    cp = Counterparty(name="тест реквизитов 1.22")
    db.add(cp)
    db.flush()
    for i, rs in enumerate(("40702810000000000001", "40702810000000000002")):
        db.add(CounterpartyBankAccount(counterparty_id=cp.id, rs=rs, bank_name="Банк", sort_order=i))
    db.flush()
    try:
        yield db, cp
    finally:
        db.rollback()
        db.close()


def _user(may_delete):
    return SimpleNamespace(id=None, role=SimpleNamespace(key="role_x"), role_id=None, _may_delete=may_delete)


def _payload(rs_list):
    return CP.CounterpartyRequisitesUpdate(bank_accounts=[{"rs": rs, "bank_name": "Банк"} for rs in rs_list])


@pytest.fixture
def perms(monkeypatch):
    monkeypatch.setattr(CP, "get_permissions_for_user",
                        lambda db, u: {"counterparties": {"view": True, "edit": True, "delete": u._may_delete}})


def test_edit_without_removing_needs_only_edit(cp_with_accounts, perms):
    db, cp = cp_with_accounts
    CP.update_counterparty_requisites(cp.id, _payload(["40702810000000000001", "40702810000000000002", "40702810000000000003"]),
                                      db, _user(False))


def test_removing_an_account_without_delete_right_is_403(cp_with_accounts, perms):
    db, cp = cp_with_accounts
    with pytest.raises(HTTPException) as e:
        CP.update_counterparty_requisites(cp.id, _payload(["40702810000000000001"]), db, _user(False))
    assert e.value.status_code == 403
    assert db.query(CounterpartyBankAccount).filter(CounterpartyBankAccount.counterparty_id == cp.id).count() == 2


def test_removing_an_account_with_delete_right_works(cp_with_accounts, perms):
    db, cp = cp_with_accounts
    CP.update_counterparty_requisites(cp.id, _payload(["40702810000000000001"]), db, _user(True))
    assert db.query(CounterpartyBankAccount).filter(CounterpartyBankAccount.counterparty_id == cp.id).count() == 1
