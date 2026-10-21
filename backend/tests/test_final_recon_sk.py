# -*- coding: utf-8 -*-
"""СК (владелец 14.10.2026): у юрлица способ и базовый %, на закрытии сделки — свои, по умолчанию от плательщика."""
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


DEAL = SimpleNamespace(id=5, payer_counterparty_id=9)
PAYER = SimpleNamespace(id=9, name="Агентство", sk_mode="скидка в счёт", sk_percent=30.0)


def test_deal_takes_payer_values_until_edited():
    s = SK.of_deal(_db(payer=PAYER), DEAL)
    assert (s["mode"], s["percent"], s["source"]) == ("скидка в счёт", 30.0, "payer")
    own = SimpleNamespace(sk_mode="постоплата", sk_percent=25.0)
    s2 = SK.of_deal(_db(row=own, payer=PAYER), DEAL)
    assert (s2["mode"], s2["percent"], s2["source"], s2["payer_percent"]) == ("постоплата", 25.0, "deal", 30.0)
    assert SK.of_deal(_db(), SimpleNamespace(id=5, payer_counterparty_id=None))["source"] == "none"


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
