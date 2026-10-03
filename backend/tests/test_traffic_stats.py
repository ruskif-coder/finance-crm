# -*- coding: utf-8 -*-
"""«Трафики → Статистика»: «кукуха» площадки за день делится между РК по их суточным
показам DSP на площадке; у Adfox база = общая (владелец 03.10.2026)."""
from datetime import date

from app.traffic import stats as st

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)


def _wire(monkeypatch, fact, totals, kuk, camps=(1, 2)):
    monkeypatch.setattr(st, "months", lambda db: ["2026-10"])
    monkeypatch.setattr(st, "current_campaigns", lambda db, allowed=None, period=None: {
        c: {"id": c, "status": "запущена", "date_start": D1, "date_end": D2, "plan_show": 0,
            "deal": f"DEAL0{c}", "deal_id": c} for c in camps})
    monkeypatch.setattr(st, "_fact", lambda db, ids: fact)
    monkeypatch.setattr(st, "_dsp_totals", lambda db, cells: totals)
    monkeypatch.setattr(st, "_kukuha", lambda db, cells: kuk)

    class _Db:
        def execute(self, *a, **k):
            class R:
                def all(self_):
                    return [(10, "farmakopeika.ru", "farmakopeika.ru", 120.0)]

                def first(self_):
                    return (D2, None)
            return R()
    return _Db()


def _f(c, pub, day, shows, adfox=False):
    return {"campaign_id": c, "publisher_id": pub, "date": day, "adfox": adfox, "shows": shows}


def test_daily_share_per_campaign(monkeypatch):
    # День 1: на площадке 10 у РК1 300, у РК2 100 (всего 400), кукуха 80 → 60 и 20.
    # День 2: только РК1 200 из 200, кукуха 50 → 50.
    db = _wire(monkeypatch,
               [_f(1, 10, D1, 300), _f(2, 10, D1, 100), _f(1, 10, D2, 200)],
               {(10, D1): 400, (10, D2): 200}, {(10, D1): 80, (10, D2): 50})
    rows = {r["campaign_id"]: r for r in st.compute(db)["rows"]}
    assert rows[1]["kukuha"] == 110 and rows[1]["total"] == 500 and rows[1]["base"] == 390
    assert rows[2]["kukuha"] == 20 and rows[2]["base"] == 80


def test_denominator_counts_all_campaigns_not_only_current(monkeypatch):
    # Текущая РК1 — 100 из 400 показов площадки за день (остальное у прошлых РК):
    # её доля кукухи 25 %, а не 100 %.
    db = _wire(monkeypatch, [_f(1, 10, D1, 100)], {(10, D1): 400}, {(10, D1): 80}, camps=(1,))
    assert st.compute(db)["rows"][0]["kukuha"] == 20


def test_adfox_has_no_kukuha(monkeypatch):
    db = _wire(monkeypatch, [_f(1, 10, D1, 500, adfox=True)], {}, {(10, D1): 80}, camps=(1,))
    r = st.compute(db)["rows"][0]
    assert (r["total"], r["adfox"], r["kukuha"], r["base"]) == (500, 500, 0, 500)


def test_kukuha_never_exceeds_campaign_shows(monkeypatch):
    db = _wire(monkeypatch, [_f(1, 10, D1, 50)], {(10, D1): 50}, {(10, D1): 999}, camps=(1,))
    assert st.compute(db)["rows"][0]["kukuha"] == 50


def test_route_has_own_permission():
    import inspect
    from app.routers import traffic_stats
    assert 'require_permission("traffic_stats", "view")' in inspect.getsource(traffic_stats)


def test_period_must_be_a_month():
    import pytest
    from fastapi import HTTPException
    from app.routers import traffic_stats
    with pytest.raises(HTTPException):
        traffic_stats.get_stats(period="2026-13", db=None, user=None)


def test_month_selects_by_deal_period():
    import inspect
    src = inspect.getsource(st.current_campaigns)
    assert "d.period_from" in src and "period_to" in src


def test_rows_carry_publisher_cpm(monkeypatch):
    db = _wire(monkeypatch, [_f(1, 10, D1, 1000)], {(10, D1): 1000}, {}, camps=(1,))
    assert st.compute(db)["rows"][0]["cpm"] == 120.0


def test_rounding_half_up_like_postgres(monkeypatch):
    """Кабинет (SQL round) и страница (Python) округляют одинаково: 2,5 → 3."""
    db = _wire(monkeypatch, [_f(1, 10, D1, 5)], {(10, D1): 10}, {(10, D1): 5}, camps=(1,))
    assert st.compute(db)["rows"][0]["kukuha"] == 3
