# -*- coding: utf-8 -*-
"""Сезонный коэффициент месяца в годовом плане (владелец 29.10.2026): частота на уника задаётся ОДНА на все месяцы
и коэффициентом не множится; CTR, CR и SOV — множатся, цена — нет. Числа руками: k = 1,5 → CTR 0,5 → 0,75, CR 2 → 3,
SOV 10 → 15, частота 3 остаётся 3. Сломать: вернуть "freq" в SEASON_FIELDS — частота станет 4,5."""
from app.routers.year_plan import _apply_season

FC = {"freq": 3, "ctr": 0.5, "cr": 2, "sov": 10, "price": 100}


def test_frequency_is_one_for_all_months_whatever_the_coefficient():
    out = _apply_season(FC, 1.5)
    assert out["freq"] == 3
    assert (out["ctr"], out["cr"], out["sov"], out["price"]) == (0.75, 3.0, 15.0, 100)


def test_reach_follows_impressions_not_the_season():
    """Охват = показы ÷ частота: при одной частоте месяц с k = 2 и тем же бюджетом даёт тот же охват, а не вдвое меньший."""
    imp = 1_000_000
    assert imp / _apply_season(FC, 2.0)["freq"] == imp / _apply_season(FC, 1.0)["freq"] == 1_000_000 / 3


def test_no_coefficient_leaves_the_forecast_as_is():
    assert _apply_season(FC, 1.0) == FC and _apply_season(FC, 1.0) is not FC
