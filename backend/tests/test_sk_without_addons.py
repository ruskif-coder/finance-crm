# -*- coding: utf-8 -*-
"""Доп. услуги СК не облагаются (владелец 07.11.2026: «все доп услуги не облагаются СК и тем более к ним не применяется скидка
в счёт»). База СК — базовая услуга сделки (сумма ДС до СК без платных допов); допы идут в ДС полной суммой.

Пример руками: базовая услуга 100 000, платный доп 20 000, «скидка в счёт» 30 % → СК 30 000 (а не 36 000),
итог ДС 90 000 = 100 000 − 30 000 + 20 000."""
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL
from app.final_recon import sk as SK
from app.master_deal import layout as LY


def _sk(mode="скидка в счёт", pct=30.0):
    return {"payer_id": 1, "payer_name": "Агентство", "payer_mode": mode, "payer_percent": pct, "rule_id": 1,
            "mode": mode, "percent": pct, "source": "rule"}


@pytest.fixture
def money(monkeypatch):
    import app.sales.mp_amounts as MA
    monkeypatch.setattr(MA, "mp_amounts_by_deal", lambda db, ids: {})
    monkeypatch.setattr(MA, "vat_pct_of", lambda deal, mp: 22.0)

    def run(mode, pct):
        monkeypatch.setattr(SK, "of_deal", lambda db, deal: _sk(mode, pct))
        pf = {"plan": 1000, "fact": None, "frozen": False}
        base = [{"amount": 100000.0}]
        extras = [{"amount": 20000.0, "bonus": False}, {"amount": 5000.0, "bonus": True}]
        return CL._money(None, SimpleNamespace(id=1), None, pf, 100000.0, base, extras, plan_only=True)
    return run


def test_discount_in_bill_is_taken_from_the_base_service_only(money):
    mo = money("скидка в счёт", 30.0)
    assert mo["sk"]["amount_net"] == 30000.0
    assert mo["total_net"] == 90000.0
    assert mo["sk"]["before_net"] == 120000.0


def test_postpay_sk_is_counted_from_the_base_service_only(money):
    mo = money("постоплата", 30.0)
    assert mo["sk"]["amount_net"] == 30000.0
    assert mo["total_net"] == 120000.0, "постоплата сумму ДС не меняет"


def test_discount_in_bill_lowers_only_the_base_service_rows():
    rows = [{"deal_id": 1, "deal": "AAA111", "brand": "Бренд", "service": "Услуга", "sk_pct": 30.0, "kind": "base", "net": 100000.0,
             "unit_price": 100.0},
            {"deal_id": 1, "deal": "AAA111", "brand": "Бренд", "service": "Услуга", "sk_pct": 30.0, "kind": "extra", "net": 20000.0,
             "unit_price": 20000.0}]
    out = LY._fold_discounts(rows)
    assert [r["net"] for r in out] == [70000.0, 20000.0]


def test_ds_of_addons_only_is_not_discounted():
    rows = [{"deal_id": 1, "deal": "AAA111", "brand": "Бренд", "service": None, "sk_pct": 30.0, "kind": "extra", "net": 20000.0,
             "unit_price": 20000.0}]
    assert LY._fold_discounts(rows) == rows


def test_agency_terms_base_is_the_base_service(monkeypatch):
    from app.agency_terms import calc as C
    from app.final_recon import closing
    monkeypatch.setattr(closing, "compute", lambda db, deal: {"base_ds_net": 100000.0, "paid_extras_net": 20000.0,
                                                              "sk": {**_sk(), "amount_net": 30000.0}})
    monkeypatch.setattr(C.R, "pick_partners", lambda rules, feat, on: [{"id": 9, "recipient_id": 2, "mode": "постоплата",
                                                                        "percent": 5.0}])
    db = SimpleNamespace(get=lambda model, i: SimpleNamespace(id=i, ord_final_contract_id=None, agency_id=None, advertiser_id=None,
                                                              brand_id=None, service_id=None))
    r = {"id": 1, "code": "AAA111", "title": "", "period": "2026-10", "agency": None, "agency_id": None, "advertiser": "Р",
         "advertiser_id": 1, "brand": "Б", "brand_id": 1, "service": "У", "entity": None, "entity_id": None,
         "contract_number": None, "contract_date": None, "contract_id": None, "master_id": None, "master_code": None}
    row = C._live_row(db, r, [])
    assert row["base_net"] == 100000.0
    assert row["partners"][0]["amount"] == 5000.0
