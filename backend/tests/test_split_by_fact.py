"""Лимит креатива — по факту (владелец 24.10.2026): креатив, добавленный в середине РК, не делит план площадки поровну
с тем, кто уже открутил часть. Лимит = свой факт + равная доля остатка; сумма = план площадки; план не ниже факта."""
from app.ad.flight import split_evenly


def _cr(i, status="запущен", fixed=None):
    return {"id": i, "creative_no": i, "status": status, "fixed": fixed}


def _plans(out):
    return {c["id"]: c["plan_show"] for c in out}


def test_new_creative_mid_rk_gets_share_of_the_rest():
    out = split_evenly(100_000, [_cr(1), _cr(2, "согласован")], facts={1: 60_000})
    assert _plans(out) == {1: 80_000, 2: 20_000}


def test_without_facts_it_is_even_as_before():
    assert _plans(split_evenly(100_000, [_cr(1), _cr(2)])) == {1: 50_000, 2: 50_000}
    assert _plans(split_evenly(100_000, [_cr(1), _cr(2)], facts={})) == {1: 50_000, 2: 50_000}


def test_overdelivered_placement_keeps_plan_at_fact():
    out = split_evenly(100_000, [_cr(1), _cr(2)], facts={1: 70_000, 2: 40_000})
    assert _plans(out) == {1: 70_000, 2: 40_000}


def test_fixed_volume_is_held_but_not_below_fact():
    out = split_evenly(100_000, [_cr(1, fixed=30_000), _cr(2), _cr(3)], facts={1: 35_000, 2: 10_000})
    p = _plans(out)
    assert p[1] == 35_000
    assert p[2] == 10_000 + 27_500 and p[3] == 27_500
    assert sum(p.values()) == 100_000


def test_rejected_creative_fact_is_spent_from_the_plan():
    out = split_evenly(100_000, [_cr(1, "отклонён"), _cr(2), _cr(3)], facts={1: 20_000})
    p = _plans(out)
    assert p[1] is None and p[2] + p[3] == 80_000
