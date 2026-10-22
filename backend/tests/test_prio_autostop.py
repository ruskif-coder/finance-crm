# -*- coding: utf-8 -*-
"""Автостоп площадки приоритезации по выполнению плана (владелец 19.10.2026, вариант 2: «останавливаем мы»).

После ночного сбора: факт площадки (сумма последних снимков по дням) ≥ цель + её доля бонусного трафика → «Стоп» в системе
с перечиткой, статус «остановлено», отметка `goal_reached_at`. Ручной «Старт» после этого — докрутка, повторно не стопим."""
from datetime import date, timedelta

from sqlalchemy import text

from app.prio import autostop as AS
from app.prio import launch as L
from app.prio import models as M
from app.prio import stats as ST
from app.prio.client import PrioApiError
from tests.test_prio import FakeApi, _approved, env  # noqa: F401 — фикстура


class DayApi(FakeApi):
    def __init__(self):
        super().__init__()
        self.daily = {}

    def stats(self, a, b):
        return {"ok": True, "stats": [{"camp_id": c, "impressions": v, "clicks": 0} for c, v in self.daily.get(a, {}).items()]}


def _live_two(db, d, pubs, api):
    a, b = _approved(db, d, pubs[0]), _approved(db, d, pubs[1])
    L.launch(db, d, a.id, client=api)
    L.launch(db, d, b.id, client=api)
    a.goal_imp, b.goal_imp = 1000, 1000
    d.bonus_traffic_mode, d.bonus_traffic_value = None, None
    db.flush()
    return a, b


def _days(api, rows):
    start = date(2026, 10, 10)
    for i, per in enumerate(rows):
        api.daily[(start + timedelta(days=i)).isoformat()] = per
    return [start + timedelta(days=i) for i in range(len(rows))]


def test_reached_goal_is_stopped_other_keeps_running(env):  # noqa: F811
    db, d, pubs = env
    api = DayApi()
    a, b = _live_two(db, d, pubs, api)
    days = _days(api, [{a.camp_id: 600, b.camp_id: 400}, {a.camp_id: 500, b.camp_id: 400}])
    ST.pull(db, api, days, commit=False)
    out = AS.run(db, api, commit=False)
    assert a.status == M.STOPPED and a.goal_reached_at and api.camps[a.camp_id]["toggle_on"] is False
    assert b.status == M.LIVE and b.goal_reached_at is None, "800 из 1000 — рано"
    assert [x["id"] for x in out["stopped"]] == [a.id] and out["stopped"][0]["fact"] == 1100


def test_regrown_day_counts_last_snapshot_not_sum(env):  # noqa: F811
    db, d, pubs = env
    api = DayApi()
    a, _ = _live_two(db, d, pubs, api)
    days = _days(api, [{a.camp_id: 600}])
    ST.pull(db, api, days, commit=False)
    api.daily[days[0].isoformat()] = {a.camp_id: 700}
    ST.pull(db, api, days, commit=False)                     # снимки 600 и 700 одного дня: факт 700, не 1300
    AS.run(db, api, commit=False)
    assert a.status == M.LIVE


def test_bonus_traffic_raises_threshold(env):  # noqa: F811
    db, d, pubs = env
    api = DayApi()
    a, _ = _live_two(db, d, pubs, api)
    d.bonus_traffic_mode, d.bonus_traffic_value = "pct", 20
    db.flush()
    ST.pull(db, api, _days(api, [{a.camp_id: 1100}]), commit=False)
    AS.run(db, api, commit=False)
    assert a.status == M.LIVE, "бонус 20 %: порог 1200, 1100 — ещё крутим"
    ST.pull(db, api, _days(api, [{a.camp_id: 1100}, {a.camp_id: 150}]), commit=False)
    AS.run(db, api, commit=False)
    assert a.status == M.STOPPED


def test_manual_start_after_autostop_is_not_stopped_again(env):  # noqa: F811
    db, d, pubs = env
    api = DayApi()
    a, _ = _live_two(db, d, pubs, api)
    ST.pull(db, api, _days(api, [{a.camp_id: 1500}]), commit=False)
    AS.run(db, api, commit=False)
    L.toggle(db, d, a.id, True, client=api)                  # аккаунт докручивает
    out = AS.run(db, api, commit=False)
    assert a.status == M.LIVE and not out["stopped"]


def test_api_failure_on_one_does_not_block_others(env):  # noqa: F811
    db, d, pubs = env
    api = DayApi()
    a, b = _live_two(db, d, pubs, api)
    ST.pull(db, api, _days(api, [{a.camp_id: 1000, b.camp_id: 1000}]), commit=False)
    real = api.update

    def flaky(cid, fields):
        if cid == a.camp_id:
            raise PrioApiError("503")
        return real(cid, fields)
    api.update = flaky
    out = AS.run(db, api, commit=False)
    assert a.status == M.LIVE and b.status == M.STOPPED
    assert [x["id"] for x in out["failed"]] == [a.id]


def test_view_shows_fact_and_reached(env):  # noqa: F811
    from app.prio import service as S
    db, d, pubs = env
    api = DayApi()
    a, _ = _live_two(db, d, pubs, api)
    ST.pull(db, api, _days(api, [{a.camp_id: 1200}]), commit=False)
    AS.run(db, api, commit=False)
    x = next(r for r in S.view(db, d)["placements"] if r["id"] == a.id)
    assert x["fact_imp"] == 1200 and x["goal_reached_at"]


def test_column_exists():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        assert s.execute(text("""SELECT 1 FROM information_schema.columns
                                  WHERE table_name = 'prio_placements' AND column_name = 'goal_reached_at'""")).first()
    finally:
        s.close()


def test_autostop_tells_account_and_site(env, monkeypatch):  # noqa: F811
    from app.notify import prio as N
    told = []
    monkeypatch.setattr(N, "goal_reached", lambda db, deal, x: told.append(("акк", x["id"])))
    monkeypatch.setattr(N, "stop_failed", lambda db, deal, x: told.append(("сбой", x["id"])))
    monkeypatch.setattr(N, "live_to_site", lambda db, deal, p, on, reason="": told.append(("площадке", p.id, on, reason)))
    monkeypatch.setattr(type(env[0]), "commit", lambda self: self.flush())   # уведомления после коммита — коммит не пишет
    db, d, pubs = env
    api = DayApi()
    a, b = _live_two(db, d, pubs, api)
    ST.pull(db, api, _days(api, [{a.camp_id: 1000, b.camp_id: 1000}]), commit=False)
    real = api.update
    api.update = lambda cid, f: (_ for _ in ()).throw(PrioApiError("503")) if cid == b.camp_id else real(cid, f)
    AS.run(db, api, commit=False, notify=True)
    assert ("акк", a.id) in told and ("площадке", a.id, False, "план показов выполнен") in told and ("сбой", b.id) in told


def test_prio_events_registered_and_in_profiles():
    from app.notify import registry
    from app.notify.seed_profiles import PLAN
    keys = ("prio_site_answered", "prio_goal_reached", "prio_stop_failed", "cron_prio_stat_failed")
    assert all(registry.get(k) for k in keys)
    planned = {k for ev in PLAN.values() for k in ev}
    assert set(keys) <= planned, f"нет в профилях: {set(keys) - planned}"
