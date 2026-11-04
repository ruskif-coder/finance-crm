# -*- coding: utf-8 -*-
"""Окно контрагента — проверки блоков «Юрлицо и реквизиты» и «Подписанты» (план 2026-11-05, Task 3).

Поломки, которые ловит: окно показывает «реквизиты в порядке», когда ДС по ним не собирается (своя копия правил вместо
`contract_check._side` и `sales/annex.party`); ноль дней отсрочки читается как «не заполнено»; истёкшая доверенность не
горит; у площадки без НДС сверка месяца считает по ставке по умолчанию молча. Всё в откатываемой транзакции.
"""
from datetime import date, timedelta

import pytest

import app.model_registry  # noqa: F401
from app.annex_tpl import contract_check
from app.database import SessionLocal
from app.models import Counterparty
from app.readiness import party as P
from app.signers.models import CounterpartySigner

ON = date(2026, 11, 4)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _cp(db, **kw):
    c = Counterparty(name=kw.pop("name", "ООО «Тест окна»"), inn=kw.pop("inn", "7707083893"), **kw)
    db.add(c)
    db.flush()
    return c


def _signer(db, cp, **kw):
    s = CounterpartySigner(counterparty_id=cp.id, director_name=kw.pop("fio", "Иванов Иван Иванович"),
                           signer_position=kw.pop("pos", "Генеральный директор"), signer_basis=kw.pop("basis", "Устава"),
                           is_default=kw.pop("is_default", True), is_archived=kw.pop("archived", False), **kw)
    db.add(s)
    db.flush()
    return s


def _ids(checks):
    return {c["id"]: c for c in checks}


def test_requisites_gaps_come_from_contract_check(db):
    cp = _cp(db, kpp=None, legal_form="ООО", term_days=30)
    got = _ids(P.cp_checks(db, cp, ON, ["agency"]))
    assert "cp.kpp" in got and got["cp.kpp"]["sev"] == "bad"
    assert got["cp.kpp"]["source"] == "annex_tpl/contract_check._side"
    assert any("КПП" in g["text"] for g in contract_check._side(cp, "заказчик")), "правило ДС то же самое"


def test_twelve_digit_inn_without_form_is_bad(db):
    cp = _cp(db, inn="500100732259", legal_form=None, term_days=30)
    c = _ids(P.cp_checks(db, cp, ON, ["contractor"]))["cp.legal_form"]
    assert c["sev"] == "bad" and "ОРД" in c["why"]
    cp.legal_form = "ИП"
    assert "cp.legal_form" not in _ids(P.cp_checks(db, cp, ON, ["contractor"]))


def test_zero_term_is_a_value(db):
    cp = _cp(db, kpp="770701001", legal_form="ООО", term_days=0)
    assert P.cp_data(db, cp)["term_days"] == 0
    assert "cp.term_days" not in _ids(P.cp_checks(db, cp, ON, ["agency"]))
    cp.term_days = None
    assert _ids(P.cp_checks(db, cp, ON, ["agency"]))["cp.term_days"]["sev"] == "warn"


def test_first_bank_account_is_main(db):
    from app.models import CounterpartyBankAccount
    cp = _cp(db, kpp="770701001")
    for i, rs in enumerate(("40702810000000000002", "40702810000000000001")):
        db.add(CounterpartyBankAccount(counterparty_id=cp.id, rs=rs, bank_name="Банк", sort_order=i))
    db.flush()
    banks = P.cp_data(db, cp)["banks"]
    assert [b["rs"] for b in banks] == ["40702810000000000002", "40702810000000000001"]
    assert [b["main"] for b in banks] == [True, False]


def test_no_default_signer_is_bad(db):
    cp = _cp(db, kpp="770701001")
    c = _ids(P.sg_checks(db, cp, ON))["sg.default"]
    assert c["sev"] == "bad" and c["source"] == "sales/annex.party"


def test_poa_expiring_and_expired(db):
    cp = _cp(db, kpp="770701001")
    _signer(db, cp)
    soon = _signer(db, cp, fio="Петрова Анна Сергеевна", basis="Доверенности № 15", is_default=False,
                   valid_until=ON + timedelta(days=16))
    gone = _signer(db, cp, fio="Сидоров Пётр Петрович", basis="Доверенности № 3", is_default=False,
                   valid_until=ON - timedelta(days=1))
    got = _ids(P.sg_checks(db, cp, ON))
    assert got[f"sg.poa.{soon.id}"]["sev"] == "warn"
    assert got[f"sg.poa.{gone.id}"]["sev"] == "bad"
    assert "sg.default" not in got


def test_archived_signer_is_not_checked(db):
    cp = _cp(db, kpp="770701001")
    _signer(db, cp)
    old = _signer(db, cp, fio="Старый Подписант", is_default=False, archived=True, valid_until=ON - timedelta(days=30))
    assert f"sg.poa.{old.id}" not in _ids(P.sg_checks(db, cp, ON))
    assert old.id in [s["id"] for s in P.sg_data(db, cp)] and next(s for s in P.sg_data(db, cp) if s["id"] == old.id)["archived"]


def test_publisher_without_vat_is_bad(db):
    cp = _cp(db, kpp="770701001", legal_form="ООО", term_days=30, vat_rate_expense=None)
    c = _ids(P.cp_checks(db, cp, ON, ["publisher"]))["cp.publisher_vat"]
    assert c["sev"] == "bad" and "сверк" in c["why"]
    assert "cp.publisher_vat" not in _ids(P.cp_checks(db, cp, ON, ["agency"]))
