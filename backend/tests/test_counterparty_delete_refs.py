# -*- coding: utf-8 -*-
"""Прибор: контрагент, на которого что-то ссылается, не удаляется (аудит 23.09.2026, 2.L5).

Одиночное удаление не проверяло ничего: у связей нет `passive_deletes`, и SQLAlchemy молча
обнуляла `counterparty_id` у операций и договоров. Массовое проверяло одни операции.
"""
import pytest
from fastapi import HTTPException

import app.notify.models  # noqa: F401
from app.database import SessionLocal
from app.models import Contract, Counterparty, User
from app.routers import counterparties as cp_api


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def admin(db):
    return db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()


def _cp(db, name):
    c = Counterparty(name=name)
    db.add(c)
    db.flush()
    return c


def test_counterparty_with_a_contract_is_not_deleted(db, admin):
    c = _cp(db, "прибор: контрагент с договором")
    db.add(Contract(counterparty_id=c.id, counterparty_name=c.name, contract_number="П-1"))
    db.flush()
    with pytest.raises(HTTPException) as e:
        cp_api.delete_counterparty(c.id, db=db, current_user=admin)
    assert e.value.status_code == 409 and "договоры" in e.value.detail
    assert db.query(Contract).filter(Contract.counterparty_id == c.id).count() == 1


def test_free_counterparty_is_deleted(db, admin):
    c = _cp(db, "прибор: свободный контрагент")
    cp_api.delete_counterparty(c.id, db=db, current_user=admin)
    assert db.query(Counterparty).filter(Counterparty.id == c.id).count() == 0


def test_payer_annex_templates_stop_the_deletion(db, admin):
    """Шаблоны ДС плательщика уходили с ним каскадом, молча: правило «каскадный ключ — это
    собственные данные» пропускало их вместе с банковскими счетами (ревью 23.09.2026).
    Собственные данные теперь — явный список; шаблоны формулировок в него не входят."""
    from app.sales.models import AnnexTemplate
    c = _cp(db, "прибор: плательщик с шаблоном")
    db.add(AnnexTemplate(payer_id=c.id, name="прибор", body="{сумма}"))
    db.flush()
    with pytest.raises(HTTPException) as e:
        cp_api.delete_counterparty(c.id, db=db, current_user=admin)
    assert e.value.status_code == 409 and "шаблоны ДС" in e.value.detail


def test_own_bank_accounts_go_with_the_counterparty(db, admin):
    from app.models import CounterpartyBankAccount
    c = _cp(db, "прибор: контрагент со счётом")
    db.add(CounterpartyBankAccount(counterparty_id=c.id, bik="044525593", rs="40702810000000000001"))
    db.flush()
    cp_api.delete_counterparty(c.id, db=db, current_user=admin)
    assert db.query(Counterparty).filter(Counterparty.id == c.id).count() == 0
