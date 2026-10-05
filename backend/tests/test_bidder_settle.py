# -*- coding: utf-8 -*-
"""Распределение объёма РК с учётом факта (владелец 05.10.2026) — первый кирпич биддера.

Правило:
  1. площадка выбыла («завершена») — её план замораживается на её факте; остальным уходит
     только неоткрученное: остаток = план РК − заданные объёмы − факт выбывших;
  2. остаток делится по весам балансировщика (балансировщик в приоритете), с потолком доли;
  3. план площадки не ниже её факта (подключилась новая и забрала долю — у старой план =
     факт, разница расходится по остальным);
  4. факта нет (статистика за вчера не пришла) — по весам, как раньше;
  5. первые 5 дней (удержание долей) факт не учитывается;
  пауза держит долю, после снятия паузы — обычный пересчёт.
"""
from datetime import date, timedelta

from app.ad.flight import distribute, flight_of
from app.bidder.rules import floor_to_fact

ON, PAUSE, OFF = "запущен", "пауза", "завершена"
START, END = date(2026, 10, 1), date(2026, 10, 30)


def _fl(day_no):
    return flight_of(START, END, START + timedelta(days=day_no - 1))


def _rows(out):
    return {r["id"]: r for r in out["rows"]}


def test_dropped_placement_keeps_its_fact_and_returns_only_the_rest():
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 2, "status": ON, "weight": 1},
           {"id": 3, "status": OFF, "weight": 1}]
    r = _rows(distribute(9000, None, _fl(10), pls, facts={1: 1000, 2: 1000, 3: 2000}))
    assert r[3]["plan_show"] == 2000, "выбывшая — план = её факт"
    assert r[1]["plan_show"] == 3500 and r[2]["plan_show"] == 3500
    assert sum(x["plan_show"] for x in r.values()) == 9000, "без перекрута"


def test_without_facts_old_behaviour():
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 3, "status": OFF, "weight": 1}]
    r = _rows(distribute(9000, None, _fl(10), pls))
    assert r[1]["plan_show"] == 9000 and r[3]["plan_show"] is None


def test_hold_days_ignore_facts():
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 3, "status": OFF, "weight": 1}]
    out = distribute(9000, None, _fl(3), pls, facts={1: 100, 3: 500})
    r = _rows(out)
    assert r[1]["plan_show"] == 9000 and r[3]["plan_show"] is None
    assert out["by_fact"] is False, "страница не должна писать «факт учтён» в дни удержания"


def test_plan_never_below_fact_when_new_placement_joins():
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 2, "status": ON, "weight": 1},
           {"id": 4, "status": ON, "weight": 2}]          # подключилась, факта нет
    r = _rows(distribute(10000, None, _fl(10), pls, facts={1: 4000, 2: 1000}))
    assert r[1]["plan_show"] == 4000, "по весам вышло бы 2500 — ниже факта"
    assert r[2]["plan_show"] == 2000 and r[4]["plan_show"] == 4000
    assert sum(x["plan_show"] for x in r.values()) == 10000


def test_pause_keeps_share():
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 2, "status": PAUSE, "weight": 1}]
    r = _rows(distribute(8000, None, _fl(10), pls, facts={1: 1000, 2: 1000}))
    assert r[1]["plan_show"] == 4000 and r[2]["plan_show"] == 4000


def test_overdelivered_pool_gives_nobody_negative():
    assert floor_to_fact(1000, {"a": 1, "b": 1}, {"a": 1500}) == {"a": 1500.0, "b": 0.0}


def test_floor_respects_cap():
    out = floor_to_fact(1000, {"a": 8, "b": 1, "c": 1}, {}, cap_abs=500)
    assert round(out["a"]) == 500 and round(out["b"]) == 250


def test_no_fresh_stats_means_by_weights(monkeypatch):
    """Ночной съём не пришёл — факт не отдаётся, раскладка по весам."""
    from app.bidder import facts as F
    monkeypatch.setattr(F, "_has_any_fact", lambda db: True)
    monkeypatch.setattr(F, "fact_as_of", lambda db: date.today() - timedelta(days=3))
    assert F.placement_facts(None, [1, 2]) is None


def test_fresh_stats_read_by_placement():
    from app.bidder.facts import placement_facts
    from app.database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        cid = db.execute(text("SELECT campaign_id FROM ad_campaign_stat "
                              "WHERE placement_id IS NOT NULL LIMIT 1")).scalar()
        got = placement_facts(db, [cid]) if cid else None
        if got is not None and cid:
            assert all(isinstance(v, int) and v >= 0 for v in got[cid].values())
    finally:
        db.close()


# ── ревью 05.10.2026 ─────────────────────────────────────────────────────────

def test_placement_with_fact_but_no_weight_keeps_its_fact():
    """Индекс сняли после того, как площадка открутила — её факт не раздаётся второй раз."""
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 2, "status": ON, "weight": None}]
    r = _rows(distribute(9000, None, _fl(10), pls, facts={2: 3000}))
    assert r[2]["plan_show"] == 3000 and r[1]["plan_show"] == 6000


def test_fixed_volume_is_floored_to_fact():
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 2, "status": ON, "weight": 1, "fixed": 1000}]
    r = _rows(distribute(9000, None, _fl(10), pls, facts={2: 1500}))
    assert r[2]["plan_show"] == 1500 and r[1]["plan_show"] == 7500


def test_hold_decided_by_separate_flight():
    """Дашборд считает темп на дату среза (вчера), а удержание — на сегодня, как ночной пересчёт."""
    pls = [{"id": 1, "status": ON, "weight": 1},
           {"id": 3, "status": OFF, "weight": 1}]
    out = distribute(9000, None, _fl(5), pls, facts={3: 500}, hold_fl=_fl(6))
    assert out["by_fact"] is True and _rows(out)[3]["plan_show"] == 500


def test_no_stats_at_all_is_not_fresh(monkeypatch):
    """Пустая база: срез «вчера» — заглушка fact_as_of, а не пришедшая статистика."""
    from app.bidder import facts as F
    monkeypatch.setattr(F, "_has_any_fact", lambda db: False)
    assert F.placement_facts(None, [1]) is None
