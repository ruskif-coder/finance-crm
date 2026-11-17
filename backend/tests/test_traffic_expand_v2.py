# -*- coding: utf-8 -*-
"""Дашборд трафика v2 (хендофф design_handoff_traffic_expand_v2, 17.11.2026): новые поля расхлопа РК.

Что ловит каждый тест — в его докстроке. Ожидаемое посчитано руками, а не той же функцией."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.ad import creative_fact
from app.traffic import expand_view as ev


def test_ctr_is_clicks_over_shows_in_percent_and_none_without_shows():
    """Поломка: CTR от плана, а не от факта, или ноль вместо прочерка у площадки без показов."""
    assert ev.ctr_of(30831, 129) == 0.42          # 129 / 30 831 = 0,418 %
    assert ev.ctr_of(0, 5) is None
    assert ev.ctr_of(None, None) is None
    assert ev.ctr_of(1000, None) == 0.0


def test_placement_gets_ctr_and_wr_mismatch_with_deal_limit():
    """Поломка: расхождение с WR по площадке считается не от НАШЕГО факта (знаменатель) или без предела сделки."""
    rows = [{"id": 1, "fact": 1000, "fact_clicks": 8}, {"id": 2, "fact": 2000, "fact_clicks": 10},
            {"id": 3, "fact": None, "fact_clicks": None}]
    out = ev.enrich_placements(rows, {1: 900, 2: 1500}, {"weborama": "10"})
    a, b, c = out
    assert a["ctr"] == 0.8 and a["wr"] == 900
    assert a["wr_mismatch"]["pct"] == 10.0 and a["wr_mismatch"]["level"] == "ok"      # (1000−900)/1000
    assert b["wr_mismatch"]["pct"] == 25.0 and b["wr_mismatch"]["level"] == "bad"     # 25 > 2×10
    assert c["ctr"] is None and c["wr"] is None and c["wr_mismatch"] is None
    assert "ctr" not in rows[0]                                                     # вход не меняется


def test_creatives_get_fact_clicks_ctr_from_counts():
    """Поломка: факт креатива берётся с площадки целиком, а не по своей строке; без факта — ноль вместо прочерка."""
    rows = [{"id": 1, "creatives": [{"id": 11}, {"id": 12}]}]
    out = ev.enrich_creatives(rows, {11: [5000, 40]})
    c11, c12 = out[0]["creatives"]
    assert (c11["fact"], c11["clicks"], c11["ctr"]) == (5000, 40, 0.8)
    assert (c12["fact"], c12["clicks"], c12["ctr"]) == (None, None, None)


class _AdfoxDb:
    def execute(self, *a, **k):
        return SimpleNamespace(all=lambda: [(11, 700, 7), (12, 300, None)])


def test_creative_counts_carry_clicks_and_totals_keep_shows_only():
    """Поломка: `totals` (раскладка лимитов DSP) начинает отдавать пары вместо показов."""
    camp = SimpleNamespace(id=1, ms_campaign_xxhash=None)
    assert creative_fact.counts(_AdfoxDb(), camp) == {11: [700, 7], 12: [300, 0]}
    assert creative_fact.totals(_AdfoxDb(), camp) == {11: 700, 12: 300}


class _RowsDb:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *a, **k):
        return SimpleNamespace(all=lambda: self.rows)


def test_rk_level_erid_and_screens_count_only_live_creatives():
    """Поломка: Е и С в строке РК считают отклонённые креативы — тогда «все с ЕРИД» никогда не наступает.
    Строки — (РК, статус, есть ЕРИД, сняты скрины)."""
    db = _RowsDb([(1, "согласован", True, True), (1, "запущен", True, False), (1, "отклонён", False, False),
                  (2, "у трафика", False, False)])
    got = ev.erid_screens_by_campaign(db, [1, 2])
    assert got[1]["erid"] == {"state": "all", "got": 2, "total": 2}
    assert got[1]["screens"] == {"state": "part", "got": 1, "total": 2}
    assert got[2]["erid"] == {"state": "none", "got": 0, "total": 1}
    assert ev.erid_screens_by_campaign(db, []) == {}
