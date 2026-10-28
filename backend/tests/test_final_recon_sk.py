# -*- coding: utf-8 -*-
"""СК (владелец 14.10.2026): у юрлица способ и базовый %, на закрытии сделки — свои, по умолчанию от плательщика."""
from datetime import date
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.final_recon import sk as SK
from app.final_recon.models import FinalReconDeal
from app.models import Counterparty


class _Q:
    def __init__(self, obj):
        self.obj = obj

    def filter(self, *a):
        return self

    def first(self):
        return self.obj


def _db(row=None, payer=None):
    added = []
    return SimpleNamespace(query=lambda m: _Q(row if m is FinalReconDeal else payer), add=added.append, added=added)


DEAL = SimpleNamespace(id=5, payer_counterparty_id=9, ord_final_contract_id=7, agency_id=3, advertiser_id=11, brand_id=21,
                       service_id=2, period_from=date(2026, 10, 1))
PAYER = SimpleNamespace(id=9, name="Агентство", sk_mode="скидка в счёт", sk_percent=30.0)
RULE = {"id": 1, "kind": "основная", "contract_id": 7, "agency_id": 3, "advertiser_id": None, "brand_id": None,
        "service_id": None, "recipient_id": None, "mode": "скидка в счёт", "percent": 12.0,
        "valid_from": date(2026, 1, 1), "valid_to": None}


def test_deal_takes_the_agency_terms_rule_until_edited(monkeypatch):
    """С 27.10.2026 СК сделки — из «Агентских условий» (правило связки договор × агентство), а не из карточки юрлица."""
    monkeypatch.setattr(SK, "_rules", lambda db: [RULE])
    s = SK.of_deal(_db(payer=PAYER), DEAL)
    assert (s["mode"], s["percent"], s["source"], s["rule_id"]) == ("скидка в счёт", 12.0, "rule", 1)
    own = SimpleNamespace(sk_mode="постоплата", sk_percent=25.0)
    s2 = SK.of_deal(_db(row=own, payer=PAYER), DEAL)
    assert (s2["mode"], s2["percent"], s2["source"], s2["payer_percent"]) == ("постоплата", 25.0, "deal", 12.0)
    monkeypatch.setattr(SK, "_rules", lambda db: [])
    s3 = SK.of_deal(_db(payer=PAYER), DEAL)
    assert s3["source"] == "none" and s3["mode"] is None          # СК юрлица больше не источник — только история


def test_set_deal_creates_row_and_validates():
    db = _db()
    r = SK.set_deal(db, DEAL, "постоплата", 27.5, SimpleNamespace(id=1))
    assert db.added == [r] and (r.deal_id, r.sk_mode, r.sk_percent, r.updated_by) == (5, "постоплата", 27.5, 1)
    for mode, pct in (("бартер", 10), ("постоплата", 101), (None, -1)):
        with pytest.raises(SK.SkError):
            SK.set_deal(_db(), DEAL, mode, pct, None)


def test_counterparty_settings():
    cp = Counterparty(name="x")
    SK.set_counterparty(cp, "скидка в счёт", 30)
    assert (cp.sk_mode, cp.sk_percent) == ("скидка в счёт", 30)


def test_sales_estimate_prefers_rule_then_agency_default(monkeypatch):
    """Дашборд продаж (бонусы) — тот же СК, что закрытие (владелец 27.10.2026: «везде из новых»); где правила нет —
    прежние 30 % агентства оценкой; прямая сделка без правила — 0."""
    monkeypatch.setattr(SK, "_rules", lambda db: [RULE])
    monkeypatch.setattr(SK, "_overrides", lambda db, ids: {6: ("постоплата", 25.0)})
    monkeypatch.setattr(SK, "_agency_defaults", lambda db: {3: 30.0, 4: 40.0})
    deals = [DEAL,                                                                  # правило 12 %
             SimpleNamespace(**{**DEAL.__dict__, "id": 6}),                         # поправка сделки 25 %
             SimpleNamespace(**{**DEAL.__dict__, "id": 7, "agency_id": 4}),         # правила нет — 40 % агентства
             SimpleNamespace(**{**DEAL.__dict__, "id": 8, "agency_id": None})]      # прямая без правила — 0
    assert SK.sales_percent_many(None, deals) == {5: 12.0, 6: 25.0, 7: 40.0, 8: 0}


def test_agency_zero_percent_stays_zero_on_dashboard(monkeypatch):
    """Поломка (ревью 27.10.2026): `pct or 30` превращал явные 0 % агентства в 30 % — бонус и «наша сумма» занижены.
    0 % — значение, а не «не задано»; 30 % — только когда у агентства процента нет вовсе."""
    monkeypatch.setattr(SK, "_rules", lambda db: [])
    monkeypatch.setattr(SK, "_overrides", lambda db, ids: {})
    monkeypatch.setattr(SK, "_agency_defaults", lambda db: {3: 0.0, 4: None})
    deals = [SimpleNamespace(**{**DEAL.__dict__, "id": 1, "agency_id": 3}), SimpleNamespace(**{**DEAL.__dict__, "id": 2, "agency_id": 4})]
    assert SK.sales_percent_many(None, deals) == {1: 0.0, 2: 30.0}


@pytest.mark.parametrize("mode,pct,want", [("постоплата", None, 0.0), (None, 25.0, 0.0), ("скидка в счёт", 25.0, 25.0)])
def test_dashboard_reads_a_partial_deal_override_like_closing(monkeypatch, mode, pct, want):
    """Поломка (ревью 27.10.2026): поправка сделки «способ без %» или «% без способа» — на закрытии СК 0 (нужны оба), а дашборд
    брал правило или % поправки. Дашборд обязан повторять закрытие: поправка есть — действует она, и СК только при обоих."""
    monkeypatch.setattr(SK, "_rules", lambda db: [RULE])
    monkeypatch.setattr(SK, "_overrides", lambda db, ids: {5: (mode, pct)})
    monkeypatch.setattr(SK, "_agency_defaults", lambda db: {})
    assert SK.sales_percent_many(None, [DEAL]) == {5: want}
