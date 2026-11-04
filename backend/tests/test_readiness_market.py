# -*- coding: utf-8 -*-
"""Окно контрагента — агентство, рекламодатели и бренды, СК, ОРД (план 2026-11-05, Task 5).

Поломки, которые ловит: у агентства появляется блок рекламодателей (а они независимы — решение владельца 04.11);
пустое юр. название красное там, где шаблон договора его не использует; бренд с ККТУ не третьего уровня считается
годным для ЕРИД; договор со сделками без регистрации в ОРД — только жёлтый; рекламодатели плательщика читаются по
запросу на каждого. Всё в откатываемой транзакции.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import app.model_registry  # noqa: F401
from app.database import SessionLocal, engine
from app.models import Contract, Counterparty
from app.readiness import market as M
from app.sales.models import (SalesAdvertiser, SalesAdvertiserCounterparty, SalesAgency, SalesAgencyCounterparty,
                              SalesBrand)

ON = date(2026, 11, 4)
_N = iter(range(10**6))


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _cp(db):
    c = Counterparty(name=f"ООО «Тест рынка {next(_N)}»", inn="7707083893", kpp="770701001")
    db.add(c)
    db.flush()
    return c


def _adv(db, cp, legal_name=None, brands=()):
    a = SalesAdvertiser(name=f"Тест-рекл {next(_N)}", short_name="Тест-рекл", legal_name=legal_name, inn="7711111111")
    db.add(a)
    db.flush()
    db.add(SalesAdvertiserCounterparty(advertiser_id=a.id, counterparty_id=cp.id))
    out = []
    for name, kktu in brands:
        b = SalesBrand(name=f"{name} {next(_N)}", advertiser_id=a.id, kktu_code=kktu)
        db.add(b)
        out.append(b)
    db.flush()
    return a, out


def _ct(db, cp, **kw):
    c = Contract(contract_number=f"Т-{next(_N)}", contract_date=date(2026, 1, 1), counterparty_id=cp.id, **kw)
    db.add(c)
    db.flush()
    return c


def _ids(checks):
    return {c["id"]: c for c in checks}


def test_advertiser_without_legal_name_is_bad_only_if_template_uses_it(db, monkeypatch):
    cp = _cp(db)
    _ct(db, cp)
    a, _ = _adv(db, cp)
    monkeypatch.setattr("app.readiness.contracts.template_tags", lambda db_, c: {"юр_название"})
    assert _ids(M.checks(db, cp, ON))[f"ad.legal_name.{a.id}"]["sev"] == "bad"
    monkeypatch.setattr("app.readiness.contracts.template_tags", lambda db_, c: {"бренд"})
    assert _ids(M.checks(db, cp, ON))[f"ad.legal_name.{a.id}"]["sev"] == "warn"


def test_brand_without_kktu_or_not_third_level_is_bad(db):
    cp = _cp(db)
    _, (none, short, ok) = _adv(db, cp, legal_name="АО «Тест»", brands=[("Без", None), ("Короткий", "12.2"), ("Годный", "12.2.2")])
    got = _ids(M.checks(db, cp, ON))
    assert got[f"ad.kktu.{none.id}"]["sev"] == "bad" and got[f"ad.kktu.{short.id}"]["sev"] == "bad"
    assert f"ad.kktu.{ok.id}" not in got and "ЕРИД" in got[f"ad.kktu.{none.id}"]["why"]


def test_agency_has_no_advertiser_block(db):
    cp = _cp(db)
    ag = SalesAgency(name=f"Тест-агентство {next(_N)}", short_name="Тест-агентство")
    db.add(ag)
    db.flush()
    db.add(SalesAgencyCounterparty(agency_id=ag.id, counterparty_id=cp.id))
    db.flush()
    assert M.ad_data(db, cp) == []
    assert M.ag_data(db, cp)["short_name"] == "Тест-агентство"


def test_many_advertisers_few_queries(db):
    cp = _cp(db)
    for _ in range(30):
        _adv(db, cp, legal_name="АО «Тест»", brands=[("Б", "12.2.2")])
    n = [0]

    def count(*a):
        n[0] += 1
    event.listen(engine, "before_cursor_execute", count)
    try:
        rows = M.ad_data(db, cp)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(rows) == 30 and all(len(r["brands"]) == 1 for r in rows)
    assert n[0] <= 3, f"запросов к базе: {n[0]} — рекламодатели читаются по одному"


def test_contract_without_ord_registration(db):
    from app.sales.models import SalesDeal
    cp = _cp(db)
    ct = _ct(db, cp)
    assert _ids(M.checks(db, cp, ON))[f"ord.contract.{ct.id}"]["sev"] == "warn"
    d = db.query(SalesDeal).first()
    was = d.ord_final_contract_id
    d.ord_final_contract_id = ct.id
    db.flush()
    assert _ids(M.checks(db, cp, ON))[f"ord.contract.{ct.id}"]["sev"] == "bad"
    d.ord_final_contract_id = was


def test_initial_contract_not_registered_is_bad(db):
    from app.ord.models import OrdInitialContract
    cp = _cp(db)
    ic = OrdInitialContract(ord_id=f"test-ic-{next(_N)}", number="ИД-1", date=date(2026, 1, 1), contractor_inn=cp.inn, advertiser_inn="7711111111",
                            advertiser_name="АО «Тест»", status="RegistrationError", error_text="нет предмета", ord_env="prod")
    db.add(ic)
    db.flush()
    c = _ids(M.checks(db, cp, ON))[f"ord.initial.{ic.id}"]
    assert c["sev"] == "bad" and "нет предмета" in c["why"]
    assert any(r["id"] == ic.id for r in M.ord_data(db, cp)["initial"])


def test_main_sk_rule_missing_and_expiring(db):
    from app.agency_terms.models import SkRule
    cp = _cp(db)
    ct = _ct(db, cp)
    assert _ids(M.checks(db, cp, ON))[f"sk.missing.{ct.id}"]["sev"] == "warn"
    ag = SalesAgency(name=f"Тест-агентство СК {next(_N)}", short_name="Тест-агентство СК")
    db.add(ag)
    db.flush()
    db.add(SalesAgencyCounterparty(agency_id=ag.id, counterparty_id=cp.id))
    r = SkRule(kind="основная", contract_id=ct.id, agency_id=ag.id, mode="постоплата", percent=15,
               valid_from=date(2026, 1, 1), valid_to=ON + timedelta(days=30))
    db.add(r)
    db.flush()
    got = _ids(M.checks(db, cp, ON))
    assert f"sk.missing.{ct.id}" not in got and got[f"sk.expiring.{r.id}"]["sev"] == "warn"
    assert any(x["id"] == r.id for x in M.sk_data(db, cp))
