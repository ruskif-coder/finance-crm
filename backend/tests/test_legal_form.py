# -*- coding: utf-8 -*-
"""Форма организации контрагента (владелец 04.11.2026, схема согласована; окно контрагента).

Поломки, которые ловит:
  * ИП с 12-значным ИНН не регистрируется в ОРД, потому что форму хранить негде;
  * форма угадывается по части слова («ООО-шка» — не ООО) или ПАО путается с АО;
  * журнал реквизитов пишет «Обновлены реквизиты» без «было → стало» — истории изменений в окне не из чего строиться.
Всё в откатываемой транзакции.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app import legal_form as LF
from app.database import SessionLocal
from app.models import Counterparty
from app.routers import counterparties as CP


@pytest.mark.parametrize("name,form", [
    ("ООО «Ромашка»", "ООО"), ("РОМАШКА ООО", "ООО"), ("ПАО Сбербанк", "ПАО"), ("АО «Фарма»", "АО"),
    ("ИП Иванов И.И.", "ИП"), ("Иванов Иван", None), ("ООО-шка Медиа", None), ("", None), (None, None),
])
def test_guess_from_name(name, form):
    assert LF.guess(name) == form


@pytest.mark.parametrize("form,code", [
    ("ООО", "JuridicalPerson"), ("АО", "JuridicalPerson"), ("ПАО", "JuridicalPerson"), ("ИП", "IndividualEntrepreneur"),
    ("самозанятый", "PhysicalPerson"), ("физлицо", "PhysicalPerson"),
    ("иностранная организация", "InternationalJuridicalPerson"), (None, None), ("ЗАО", None),
])
def test_ord_code(form, code):
    assert LF.ord_code(form) == code


def test_forms_are_the_agreed_list():
    assert LF.FORMS == ("ООО", "АО", "ПАО", "ИП", "самозанятый", "физлицо", "иностранная организация")


@pytest.fixture
def cp(monkeypatch):
    db = SessionLocal()
    monkeypatch.setattr(db, "commit", db.flush)
    logged = []
    monkeypatch.setattr(CP, "log_action", lambda db_, user, action, **k: logged.append((action, k.get("details"))))
    c = Counterparty(name="тест формы организации", inn="7700000001")
    db.add(c)
    db.flush()
    try:
        yield db, c, logged
    finally:
        db.rollback()
        db.close()


def _user():
    return SimpleNamespace(id=None, name="тест", role=SimpleNamespace(key="admin"), role_id=None)


def test_requisites_accept_form_and_place_and_log_before_after(cp):
    db, c, logged = cp
    CP.update_counterparty_requisites(c.id, CP.CounterpartyRequisitesUpdate(
        inn="7700000001", kpp="770001001", legal_form="ИП", signed_place="г. Казань"), db, _user())
    assert (c.legal_form, c.signed_place) == ("ИП", "г. Казань")
    details = " ".join(d or "" for a, d in logged if a == "update_counterparty_requisites")
    assert "форма: — → ИП" in details and "место подписания: — → г. Казань" in details and "КПП: — → 770001001" in details


def test_fields_not_sent_are_not_cleared(cp):
    """Форма и место подписания — новые поля: старые экраны их не шлют и не должны стирать."""
    db, c, _ = cp
    c.legal_form, c.signed_place = "ООО", "г. Москва"
    db.flush()
    CP.update_counterparty_requisites(c.id, CP.CounterpartyRequisitesUpdate(inn="7700000001"), db, _user())
    assert (c.legal_form, c.signed_place) == ("ООО", "г. Москва")


def test_unknown_form_is_refused(cp):
    db, c, _ = cp
    with pytest.raises(HTTPException) as e:
        CP.update_counterparty_requisites(c.id, CP.CounterpartyRequisitesUpdate(inn="7700000001", legal_form="ЗАО"), db, _user())
    assert e.value.status_code == 400


def test_fixing_an_account_number_is_an_edit_not_a_removal(cp, monkeypatch):
    """Ревью 05.11.2026: счёт узнавался по р/с, и исправление опечатки в р/с считалось «убрать счёт» — 403 у роли без права
    «удаление» (аккаунт). Убрать — это когда счетов стало меньше."""
    from fastapi import HTTPException
    from app.models import CounterpartyBankAccount
    db, c, _ = cp
    db.add(CounterpartyBankAccount(counterparty_id=c.id, bank_name="Банк", rs="40702810000000000001", sort_order=0))
    db.flush()
    monkeypatch.setattr(CP, "get_permissions_for_user", lambda db_, u: {"counterparties": {"edit": True, "delete": False}})
    clerk = SimpleNamespace(id=None, name="тест", role=SimpleNamespace(key="role_8"), role_id=None)
    acc = CP.BankAccountData(bank_name="Банк", rs="40702810000000000009")
    CP.update_counterparty_requisites(c.id, CP.CounterpartyRequisitesUpdate(inn="7700000001", bank_accounts=[acc]), db, clerk)
    assert [a.rs for a in db.query(CounterpartyBankAccount).filter_by(counterparty_id=c.id)] == ["40702810000000000009"]
    with pytest.raises(HTTPException) as e:
        CP.update_counterparty_requisites(c.id, CP.CounterpartyRequisitesUpdate(inn="7700000001", bank_accounts=[]), db, clerk)
    assert e.value.status_code == 403
