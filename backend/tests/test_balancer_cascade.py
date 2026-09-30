# -*- coding: utf-8 -*-
"""Балансировщик «A + D» (владелец 30.09.2026): каскад индекса, коридор по SimilarWeb,
потолок доли площадки в РК. Чистые функции — без базы."""
import pytest

from app.ad.balance import SW_CORRIDOR, calibrate, compute_index, swtraffic
from app.ad.flight import capped_shares, distribute

K = {"k_sw": 10.0, "k_vol_web": 5.0, "k_vol_app": 2.0}


def test_swtraffic_formula_and_incomplete_data():
    assert swtraffic(1000, 3, 20) == pytest.approx(2400)       # 1000 × 3 × 80 / 100
    assert swtraffic(1000, 3, None) is None, "без BR оценку не выдумываем"
    assert swtraffic(None, 3, 20) is None


def test_cascade_order_requests_then_sw_then_volume():
    a = compute_index(50_000, 4_000, 999, "web", K)
    assert (a["value"], a["confidence"], a["source"]) == (50_000, "A", "ad_requests")
    b = compute_index(None, 4_000, 999, "web", K)
    assert (b["value"], b["confidence"], b["source"]) == (40_000, "B", "similarweb")
    c = compute_index(None, None, 1_000, "app_ios", K)
    assert (c["value"], c["confidence"]) == (2_000, "C"), "у app свой k объёма"
    assert compute_index(None, None, None, "web", K)["value"] is None


def test_corridor_clamps_both_ways_and_flags():
    est = 4_000 * K["k_sw"]
    hi = compute_index(est * 50, 4_000, None, "web", K)
    assert hi["value"] == pytest.approx(est * SW_CORRIDOR) and hi["flag"] == "high"
    assert hi["source"] == "req_sw_clamp"
    lo = compute_index(est / 50, 4_000, None, "web", K)
    assert lo["value"] == pytest.approx(est / SW_CORRIDOR) and lo["flag"] == "low"
    ok = compute_index(est * 2, 4_000, None, "web", K)
    assert ok["value"] == est * 2 and ok["flag"] is None


def test_calibration_is_median_of_pairs_with_both_numbers():
    raw = [{"requests": 10, "sw": 1, "volume": 2, "scope": "web"},
           {"requests": 30, "sw": 1, "volume": 3, "scope": "web"},
           {"requests": 1000, "sw": 1, "volume": None, "scope": "web"},   # выброс
           {"requests": None, "sw": 5, "volume": 5, "scope": "web"}]
    k = calibrate(raw)
    assert k["k_sw"] == 30, "медиана, а не среднее: выброс 1000 не утаскивает k"
    assert k["k_vol_web"] == pytest.approx(7.5) and k["k_vol_app"] is None


def test_cap_redistributes_and_keeps_total():
    sh = capped_shares({"a": 50, "b": 30, "c": 10, "d": 10}, 0.3)
    assert sh["a"] == pytest.approx(0.3) and sh["b"] == pytest.approx(0.3)
    assert sh["c"] == pytest.approx(0.2) and sum(sh.values()) == pytest.approx(1)


def test_manual_index_is_not_capped():
    sh = capped_shares({"a": 50, "b": 30, "c": 10, "d": 10}, 0.3, capless={"a"})
    assert sh["a"] == pytest.approx(0.5)


def test_infeasible_cap_rises_to_equal_share_so_volume_is_not_lost():
    sh = capped_shares({"a": 90, "b": 10}, 0.15)
    assert sh == {"a": pytest.approx(0.5), "b": pytest.approx(0.5)}


def test_infeasible_cap_raise_ignores_capless_placement():
    """Ревью 30.09: подъём невыполнимого потолка считался и по ручной площадке — та
    получала треть объёма при крошечном весе."""
    sh = capped_shares({"a": 50, "b": 50, "m": 1}, 0.15, capless={"m"})
    assert sh["m"] == pytest.approx(1 / 101), "ручная держит долю по весу"
    assert sh["a"] == pytest.approx(sh["b"]) and sum(sh.values()) == pytest.approx(1)


def test_distribute_applies_cap_to_campaign_plan():
    pls = [{"id": i, "status": "запущен", "weight": w} for i, w in enumerate([60, 20, 10, 5, 5])]
    rows = distribute(1000, None, None, pls, cap=0.3)["rows"]
    assert rows[0]["plan_show"] == 300 and sum(r["plan_show"] or 0 for r in rows) == 1000
    free = distribute(1000, None, None, pls)["rows"]
    assert free[0]["plan_show"] == 600, "без потолка — как раньше"
