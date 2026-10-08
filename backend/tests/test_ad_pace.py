# -*- coding: utf-8 -*-
"""Оценка темпа площадки (08.10.2026): статусы суток, хронический недобор, возможность в день."""
from datetime import date, timedelta

import pytest

from app.ad import pace

END = date(2026, 10, 30)
D = date(2026, 10, 10)


@pytest.mark.parametrize("shows,offered,need,want", [
    (100, 500, 100, pace.IN_PACE),
    (89, 500, 100, pace.NOT_DELIVERED),        # меньше 90 %, трафик был
    (90, 500, 100, pace.IN_PACE),
    (111, 500, 100, pace.OVER),
    (50, 60, 100, pace.LITTLE),                # предложено меньше нужного
    (0, 0, 100, pace.NO_TRAFFIC),
    (50, None, 100, pace.SHORT),               # Adfox: причины нет
    (0, None, 100, pace.SHORT),                # не знаем, предложено ли: не «нет трафика»
    (0, 0, 0, pace.IN_PACE),                   # нужного нет — план закрыт
])
def test_day_status(shows, offered, need, want):
    assert pace.status_of(shows, offered, need) == want


def test_need_is_the_rest_over_days_to_the_end():
    assert pace.need_on(3000, 1000, date(2026, 10, 20), END) == pytest.approx(2000 / 11)
    assert pace.need_on(1000, 2000, D, END) == 0              # факт выше плана


def _days(rows):
    return {D + timedelta(days=i): r for i, r in enumerate(rows)}


def test_assess_reports_the_last_day_and_capacity():
    days = _days([(100, 400)] * 5)
    out = pace.assess(2100, days, END, D + timedelta(days=4))
    assert out["day"] == D + timedelta(days=4) and out["shows"] == 100 and out["offered"] == 400
    assert out["capacity"] == 400 and out["chronic"] is False


def test_chronic_is_three_underdelivered_days_of_five():
    days = _days([(10, 800), (10, 800), (600, 800), (10, 800), (600, 800)])
    out = pace.assess(10000, days, END, D + timedelta(days=4))
    assert out["chronic"] is True and out["status"] == pace.IN_PACE
    two = _days([(10, 800), (600, 800), (600, 800), (10, 800), (600, 800)])
    assert pace.assess(10000, two, END, D + timedelta(days=4))["chronic"] is False


def test_nothing_to_judge_returns_none():
    assert pace.assess(None, _days([(1, 1)]), END, D) is None
    assert pace.assess(1000, {}, END, D) is None
    assert pace.assess(1000, _days([(1, 1)]), None, D) is None
    # срез ещё не дошёл до первых суток РК
    assert pace.assess(1000, _days([(1, 1)]), END, D - timedelta(days=1)) is None


def test_capacity_ignores_days_without_the_offered_figure():
    days = _days([(5, None), (5, 100), (5, 300), (5, None), (5, 200)])
    assert pace.assess(10000, days, END, D + timedelta(days=4))["capacity"] == 200
