# -*- coding: utf-8 -*-
"""Шаги раскладки объёма по площадкам (`ad/flight.distribute`, разбита 07.10.2026).

`distribute` была одной функцией сложности 62 (самая сложная в денежной логике биддера). Перед правкой
новая версия сверена со старой на 40 000 случайных входах без единого расхождения (дробные числа совпали
бит в бит); общую картину держит `tests/test_ad_flight.py`, а здесь — каждый шаг отдельно, чтобы правка одного
правила (например, ставки биддера после 15.10) ломала один маленький тест, а не «где-то в раскладке».
"""
from datetime import date, timedelta

import pytest

from app.ad import flight as F

TODAY = date(2026, 10, 7)


def _running_flight():
    """РК идёт 10-й день: удержание долей (первые пять дней) кончилось."""
    return F.flight_of(TODAY - timedelta(days=9), TODAY + timedelta(days=20), TODAY)


def _holding_flight():
    return F.flight_of(TODAY - timedelta(days=1), TODAY + timedelta(days=28), TODAY)


def P(i, status="запущен", weight=1, **kw):
    return {"id": i, "status": status, "weight": weight, **kw}


# ── шаг 1: заданный объём ────────────────────────────────────────────────────

def test_fixed_volume_is_raised_to_the_fact_only_when_settling():
    a, b = P(1, fixed=500), P(2, fixed=0)
    fact = {id(a): 800.0, id(b): 300.0}
    assert F._fixed_volumes([a, b], fact, settle=True) == {id(a): 800.0, id(b): 0.0}
    assert F._fixed_volumes([a, b], fact, settle=False) == {id(a): 500.0, id(b): 0.0}


def test_fixed_volume_above_the_fact_stays():
    a = P(1, fixed=1000)
    assert F._fixed_volumes([a], {id(a): 200.0}, settle=True) == {id(a): 1000.0}


# ── шаг 2: выбывшие площадки держат свой факт ────────────────────────────────

def test_a_finished_placement_with_a_fact_holds_its_fact():
    done = P(1, status="завершена", weight=2)
    live = P(2)
    fact = {id(done): 700.0, id(live): 100.0}
    fixed = {id(done): 0.0, id(live): 0.0}
    out = F._dropped_volumes([done, live], fact, fixed, F.PLACEMENT_IN_PLAN, settle=True)
    assert out == {id(done): 700.0}


def test_a_placement_that_lost_its_weight_but_delivered_holds_its_fact_too():
    p = P(1, weight=None)
    assert F._dropped_volumes([p], {id(p): 50.0}, {id(p): 0.0}, F.PLACEMENT_IN_PLAN, True) == {id(p): 50.0}


def test_nothing_is_dropped_before_the_fact_counts():
    done = P(1, status="завершена")
    assert F._dropped_volumes([done], {id(done): 700.0}, {id(done): 0.0}, F.PLACEMENT_IN_PLAN, False) == {}


# ── шаг 3: раскладка целиком ─────────────────────────────────────────────────

def test_rest_is_the_plan_minus_fixed_and_dropped():
    fixed, done, live = P(1, fixed=2000), P(2, status="завершена"), P(3)
    lay = F._layout(10000, _running_flight(), [fixed, done, live], None, {2: 1500, 3: 0}, None)
    assert lay.settle and lay.rest == 10000 - 2000 - 1500
    assert lay.dropped == {id(done): 1500.0}
    assert set(lay.w_of) == {id(live)}


def test_during_the_hold_everyone_in_work_shares_and_the_fact_is_ignored():
    wait, run = P(1, status="ждёт запуска", weight=1), P(2, weight=3)
    lay = F._layout(1000, _holding_flight(), [wait, run], None, {1: 10, 2: 20}, None)
    assert not lay.settle and lay.dropped == {}
    assert lay.w_of[id(wait)] == pytest.approx(0.25) and lay.w_of[id(run)] == pytest.approx(0.75)


def test_without_a_plan_the_rest_is_zero_and_shares_follow_weights():
    a, b = P(1, weight=1), P(2, weight=3)
    lay = F._layout(None, _running_flight(), [a, b], None, None, None)
    assert lay.rest == 0.0 and lay.w_sum == 4.0


# ── шаг 4: план и доля одной площадки — порядок приоритета ───────────────────

def _lay(**kw):
    base = dict(settle=False, in_plan_set=F.PLACEMENT_IN_PLAN, fixed_of={}, dropped={}, rest=1000.0,
                w_sum=4.0, w_of={})
    base.update(kw)
    return F._Layout(**base)


def test_stored_values_beat_everything():
    p = P(1, plan_stored=1234.4, share_stored=0.3)
    lay = _lay(dropped={id(p): 500.0}, w_of={id(p): 0.5})
    assert F._plan_and_share(p, lay, 2000, True, True, False, 700.0) == (1234, 0.3)


def test_dropped_beats_fixed_and_weights():
    p = P(1)
    lay = _lay(dropped={id(p): 500.0}, w_of={id(p): 0.5})
    assert F._plan_and_share(p, lay, 2000, False, True, False, 700.0) == (500, 0.25)


def test_fixed_beats_weights():
    p = P(1)
    lay = _lay(w_of={id(p): 0.5})
    assert F._plan_and_share(p, lay, 2000, False, True, False, 700.0) == (700, 0.35)


def test_weights_split_the_rest_and_no_plan_means_share_by_weight():
    p = P(1)
    lay = _lay(w_of={id(p): 0.25})
    assert F._plan_and_share(p, lay, 2000, False, True, False, 0.0) == (250, 250.0 * 1 / 2000)
    assert F._plan_and_share(p, lay, None, False, True, False, 0.0) == (250, 0.25)


def test_a_placement_outside_the_plan_gets_nothing():
    p = P(1, status="завершена")
    assert F._plan_and_share(p, _lay(w_of={id(p): 0.5}), 2000, False, False, False, 0.0) == (None, 0.0)


# ── итог по-прежнему согласован ──────────────────────────────────────────────

def test_distribute_still_adds_up_to_the_plan():
    pl = [P(1, weight=1), P(2, weight=2), P(3, weight=1, fixed=1000)]
    out = F.distribute(10000, None, _running_flight(), pl)
    assert sum(r["plan_show"] for r in out["rows"]) == 10000
    assert out["share_sum"] == pytest.approx(1.0)
