# -*- coding: utf-8 -*-
"""Цена единицы и план/факт закупленной метрики в реестре сделок (владелец 28.09.2026)."""
from app.sales import deal_units as U


def _r(model, volume, price, discount=0):
    return {"model": model, "volume": volume, "unit_price": price, "discount": discount}


def test_cpm_plan_is_shows_and_fact_is_shows():
    u = U.summarize([_r("CPM", 1_000_000, 365)], {"shows": 400_000, "clicks": 900})
    assert (u["model"], u["price_min"], u["price_max"]) == ("CPM", 365, 365)
    assert (u["metric"], u["plan"], u["fact"]) == ("shows", 1_000_000, 400_000)


def test_cpc_plan_is_clicks():
    u = U.summarize([_r("CPC", 5000, 30)], {"shows": 400_000, "clicks": 900})
    assert (u["metric"], u["plan"], u["fact"]) == ("clicks", 5000, 900)


def test_fix_has_price_but_no_plan_fact():
    u = U.summarize([_r("Fix", 1, 80000)], {"shows": 10})
    assert u["price_min"] == 80000 and u["metric"] is None and u["plan"] is None


def test_different_prices_give_a_range_not_a_pick():
    u = U.summarize([_r("CPM", 100_000, 300), _r("CPM", 100_000, 365)])
    assert (u["price_min"], u["price_max"]) == (300, 365)
    assert u["plan"] == 200_000 and u["fact"] is None, "нет статистики — «не пришло», а не 0"


def test_mixed_models_take_the_bigger_budget_and_say_so():
    u = U.summarize([_r("CPM", 1_000_000, 300), _r("CPC", 100, 30)])   # 300 000 против 3 000
    assert u["model"] == "CPM" and u["mixed"] is True


def test_empty_plan_is_nothing():
    assert U.summarize([]) == {}
