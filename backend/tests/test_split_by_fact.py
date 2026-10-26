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


# Ручной план площадки («Перераспределить», 24.10.2026) и объёмы по креативам (владелец 26.10.2026: «пропорционально»):
# объёмы креативов масштабируются к новому плану площадки в своей пропорции. Без этого перенос до DSP не доходил —
# план площадки 20 000, а лимиты оставались 15 000 + 15 000.
def test_manual_plan_scales_creative_volumes_down():
    out = split_evenly(20_000, [_cr(1, fixed=15_000), _cr(2, fixed=15_000)], facts={1: 5_000, 2: 5_000}, manual=True)
    assert _plans(out) == {1: 10_000, 2: 10_000}


def test_manual_plan_scales_creative_volumes_up_in_their_proportion():
    out = split_evenly(40_000, [_cr(1, fixed=15_000), _cr(2, fixed=15_000)], manual=True)
    assert _plans(out) == {1: 20_000, 2: 20_000}
    out = split_evenly(20_000, [_cr(1, fixed=10_000), _cr(2, fixed=30_000)], manual=True)
    assert _plans(out) == {1: 5_000, 2: 15_000}


def test_scaled_volume_still_not_below_fact():
    out = split_evenly(20_000, [_cr(1, fixed=15_000), _cr(2, fixed=15_000)], facts={1: 12_000, 2: 1_000}, manual=True)
    assert _plans(out)[1] == 12_000


def test_without_manual_plan_creative_volumes_hold_as_entered():
    out = split_evenly(20_000, [_cr(1, fixed=15_000), _cr(2, fixed=15_000)], facts={1: 5_000, 2: 5_000})
    assert _plans(out) == {1: 15_000, 2: 15_000}


def test_manual_scaling_leaves_room_for_spent_and_free_creatives():
    """Ревью 26.10.2026: масштаб к ВСЕМУ плану площадки забывал открученное отклонённым и креативами без объёма — лимиты
    в сумме выходили больше плана. Масштаб — к остатку: план − открученное вне работы − факт креативов без объёма."""
    crs = [_cr(1, fixed=15_000), _cr(2, "отклонён"), _cr(3)]
    out = _plans(split_evenly(20_000, crs, facts={1: 5_000, 2: 3_000, 3: 1_000}, manual=True))
    assert out[1] == 16_000 and out[3] == 1_000
    assert out[1] + out[3] + 3_000 == 20_000                          # с открученным отклонённым — ровно план
