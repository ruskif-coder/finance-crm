# -*- coding: utf-8 -*-
"""План дня с учётом недокрута прошлых дней — на дашборде трафика (график и стена дней), владелец 13.10.2026.

Правило ровно то же, что в «Отчёте по РК» (`frontend/lib/rkAnalysis.mjs`, `planFor`; те же числа в `rkAnalysis.test.mjs`):
цель дня = (план − факт ДО этого дня) ÷ дни до конца флайта, считая этот; нулевые дни растят план следующих, перекрут
(в том числе после «темпа размещения») снижает; ниже нуля не уходит; в дни окна буста — плюс процент буста.
Будущие дни — как и раньше «нужно в день». Два места, одно правило: числа здесь и в JS-тесте обязаны совпадать.
"""
from datetime import date, timedelta

import pytest

from app.ad import day_plan
from app.ad.flight import daily_buckets, flight_of

D1 = date(2026, 10, 1)
FL = flight_of(D1, date(2026, 10, 10), date(2026, 10, 5))        # 10 дней, отчитано 5
FACTS = {D1 + timedelta(days=i): (1500, 10) for i in range(5)}    # 1500 в день первые пять дней
PLAN = 30000


def test_past_goals_grow_with_the_shortfall_and_match_the_report():
    g = day_plan.past_goals(PLAN, FL, FACTS, date(2026, 10, 5))
    assert [round(g[D1 + timedelta(days=i)], 2) for i in range(5)] == [
        3000.0, round(28500 / 9, 2), 3375.0, round(25500 / 7, 2), 4000.0]
    assert date(2026, 10, 6) not in g                              # будущее не считаем


def test_zero_start_makes_each_next_day_bigger():
    g = day_plan.past_goals(PLAN, FL, {}, date(2026, 10, 5))        # РК не стартовала
    vals = [g[D1 + timedelta(days=i)] for i in range(5)]
    assert vals == sorted(vals) and vals[0] == 3000 and vals[1] > 3000


def test_overdelivery_lowers_the_following_days_and_never_goes_negative():
    over = {D1 + timedelta(days=i): (50000, 0) for i in range(5)}
    g = day_plan.past_goals(PLAN, FL, over, date(2026, 10, 5))
    assert all(v >= 0 for v in g.values()) and g[date(2026, 10, 5)] == 0


def test_boost_days_raise_the_goal_by_the_percent():
    base = day_plan.past_goals(PLAN, FL, FACTS, date(2026, 10, 5))
    boosted = day_plan.past_goals(PLAN, FL, FACTS, date(2026, 10, 5), {date(2026, 10, 3): 20, date(2026, 10, 4): 20})
    assert boosted[date(2026, 10, 3)] == pytest.approx(base[date(2026, 10, 3)] * 1.2)
    assert boosted[date(2026, 10, 2)] == base[date(2026, 10, 2)]
    assert boosted[date(2026, 10, 5)] == base[date(2026, 10, 5)]


def test_chart_buckets_use_the_goals_for_past_days_and_need_for_future():
    out = daily_buckets(PLAN, 7500, FL, FACTS, "day", today=date(2026, 10, 5))
    plans = [b["plan"] for b in out["buckets"]]
    assert plans[:5] == [3000, round(28500 / 9), 3375, round(25500 / 7), 4000]
    assert plans[5:] == [4500] * 5                                  # (30000 − 7500) ÷ 5 — «нужно в день»
    assert all(b["repaced"] for b in out["buckets"][1:])            # день 1 совпал с исходным, дальше — пересчёт


def test_week_bucket_sums_daily_goals():
    out = daily_buckets(PLAN, 7500, FL, FACTS, "week", today=date(2026, 10, 5))
    first = out["buckets"][0]                                       # 1–7 октября: 5 прошлых дней + 2 будущих
    assert first["plan"] == round(3000 + 28500 / 9 + 3375 + 25500 / 7 + 4000 + 4500 * 2)


def test_chart_boost_days_in_the_past_raise_the_bar():
    base = daily_buckets(PLAN, 7500, FL, FACTS, "day", today=date(2026, 10, 5))
    boosted = daily_buckets(PLAN, 7500, FL, FACTS, "day", today=date(2026, 10, 5),
                            boost_days={date(2026, 10, 3): 20})
    assert boosted["buckets"][2]["plan"] == round(3375 * 1.2)
    assert boosted["buckets"][1]["plan"] == base["buckets"][1]["plan"]


def test_wall_cells_carry_the_same_daily_plan():
    from app.routers.traffic_dashboard import _day_wall
    row = {"id": 1, "deal_code": "T1", "date_start": D1, "date_end": date(2026, 10, 10), "plan_show": PLAN,
           "done_pct": 25, "product": "x"}
    wall = _day_wall([row], {1: FACTS}, date(2026, 10, 5))
    cells = wall[0]["cells"]
    assert [c["plan"] for c in cells[:5]] == [3000, round(28500 / 9), 3375, round(25500 / 7), 4000]
    assert cells[5]["plan"] == 4500 and cells[5]["ahead"] is True
    assert cells[4]["ratio"] == round(1500 / 4000, 3)                # факт ÷ план ЭТОГО дня


def test_boost_windows_come_from_the_single_definition():
    from app.ad import boost
    from datetime import datetime
    row = dict(pct=20, days=2, starts_on=date(2026, 10, 8), until=date(2026, 10, 10), ended_at=datetime(2026, 10, 11, 2), ended_reason="истёк")
    w = boost.boost_window(row)
    assert w == {"pct": 20, "from": "2026-10-09", "to": "2026-10-10"}
    assert boost.days_pct([w]) == {date(2026, 10, 9): 20, date(2026, 10, 10): 20}
