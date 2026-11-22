# -*- coding: utf-8 -*-
"""«Проверка РК»: проверки — чистые функции от собранной РК, поэтому проверяются без базы.
Случаи взяты из живых находок 11.10.2026 (прод v2.6.80): РК крутит, а в базе «ожидает сборки»;
Weborama насчитывает больше нашего; площадка вне DSP без пикселя; внешний пиксель."""
from datetime import date, timedelta

from app.ad import rk_check as R
from app.routers.rk_check import since_of

AS_OF = date(2026, 10, 10)


def pl(pid, status="запущен", pixel=True, share=None, plan=None, creatives=None):
    return {"id": pid, "name": f"site{pid}.ru", "status": status, "pixel": pixel, "share": share,
            "plan_show": plan, "creatives": creatives if creatives is not None else [{"hash": f"H{pid}", "erid": "E"}]}


def camp(**kw):
    base = dict(id=1, code="TEST01", title="t", status="запущена", date_start=date(2026, 10, 1),
                date_end=date(2026, 10, 31), plan_show=1_000_000, ms_hash="CAMP", goals={}, px_on=True,
                px_mode="own", px_tag=False, as_of=AS_OF, stale=False)
    base.update(kw)
    return R.Camp(**base)


def days(n_from=1, n_to=10, shows=1000):
    return {date(2026, 10, d): shows for d in range(n_from, n_to + 1)}


# ── заведение ──
def test_running_in_dsp_but_deal_behind_the_placement_stage_is_red():
    c = camp(placements=[pl(1)], stage_name="Готовятся к старту", stage_behind=True)
    r = R.check_stage_sync(c)
    assert r.level == R.RED and "Готовятся к старту" in r.message


def test_running_and_deal_in_placement_is_green():
    c = camp(placements=[pl(1)], stage_name="В размещении", stage_behind=False)
    assert R.check_stage_sync(c).level == R.GREEN


def test_stored_campaign_status_is_not_compared():
    """Хранимое «ожидает сборки» у крутящейся РК — заглушка, экраны считают статус по площадкам
    (11.10.2026: 9 таких РК, у всех сделка в размещении). Проверка на него не смотрит."""
    c = camp(status="ожидает сборки", placements=[pl(1)], stage_name="В размещении")
    assert R.check_stage_sync(c).level == R.GREEN


def test_stage_check_skips_when_nobody_runs_in_dsp():
    assert R.check_stage_sync(camp(placements=[pl(1, status="ждёт сборки")], stage_behind=True)).level == R.SKIP
    assert R.check_stage_sync(camp(placements=[pl(1)], ms_hash=None, stage_behind=True)).level == R.SKIP


def test_no_dsp_campaign_with_running_placements_is_red():
    assert R.check_dsp_campaign(camp(ms_hash=None, placements=[pl(1)])).level == R.RED
    assert R.check_dsp_campaign(camp(ms_hash=None, placements=[pl(1, status="ждёт сборки")])).level == R.SKIP


def test_own_pixel_missing_only_matters_where_it_delivers():
    c = camp(placements=[pl(1, pixel=False), pl(2, pixel=False), pl(3)], dsp_days={1: days()})
    r = R.check_pixel(c)
    assert r.level == R.RED and [i.placement_id for i in r.items] == [1]      # 2 не откручивает — не вина пикселя


def test_pixel_modes():
    assert R.check_pixel(camp(px_on=False)).level == R.SKIP
    assert R.check_pixel(camp(px_mode="external", px_tag=False)).level == R.RED
    assert R.check_pixel(camp(px_mode="external", px_tag=True)).level == R.GREEN


def test_erid_missing_on_creative_in_dsp():
    c = camp(placements=[pl(1, creatives=[{"hash": "H", "erid": None}]), pl(2)])
    r = R.check_erid(c)
    assert r.level == R.RED and r.items[0].placement_id == 1
    assert R.check_erid(camp(placements=[pl(2)])).level == R.GREEN
    assert R.check_erid(camp(placements=[pl(3, creatives=[])])).level == R.SKIP


# ── сбор ──
def test_stale_fact_is_red():
    assert R.check_fact_fresh(camp(stale=True)).level == R.RED
    assert R.check_fact_fresh(camp()).level == R.GREEN


def test_delivery_yesterday_partial_and_total():
    d = {1: days(), 2: {**days(1, 9)}}                    # у второй нет 10.10
    r = R.check_delivery(camp(placements=[pl(1), pl(2)], dsp_days=d))
    assert r.level == R.YELLOW and [i.placement_id for i in r.items] == [2]
    r = R.check_delivery(camp(placements=[pl(1), pl(2)], dsp_days={1: days(1, 9), 2: days(1, 9)}))
    assert r.level == R.RED


def test_delivery_skips_placements_outside_dsp():
    c = camp(placements=[pl(1, creatives=[])], dsp_days={})
    assert R.check_delivery(c).level == R.SKIP


def test_gap_inside_period_is_found_edges_are_not():
    d = days()
    del d[date(2026, 10, 5)]
    r = R.check_gaps(camp(placements=[pl(1)], dsp_days={1: d}))
    assert r.level == R.YELLOW and r.items[0].value["days"] == ["2026-10-05"]
    assert R.check_gaps(camp(placements=[pl(1)], dsp_days={1: days(3, 10)})).level == R.GREEN


def test_wr_mismatch_uses_dashboard_rule():
    own = {1: 1000, 2: 1000}
    ok = camp(own_total=2000, own_by_pl=own, ver={"shows": 1900, "by_placement": {1: 950, 2: 950}})
    assert R.check_wr_mismatch(ok).level == R.GREEN                       # 5 % при пороге 10
    warn = camp(own_total=2000, own_by_pl=own, ver={"shows": 1700, "by_placement": {1: 900, 2: 800}})
    assert R.check_wr_mismatch(warn).level == R.YELLOW                    # 15 %
    higher = camp(own_total=2000, own_by_pl=own, ver={"shows": 2200, "by_placement": {1: 1100, 2: 1100}})
    assert R.check_wr_mismatch(higher).level == R.GREEN                   # Weborama на 10 % больше — в пределах порога
    way_higher = camp(own_total=2000, own_by_pl=own, ver={"shows": 2300, "by_placement": {1: 1150, 2: 1150}})
    assert R.check_wr_mismatch(way_higher).level == R.YELLOW              # 15 % выше: за порогом, меньше двух порогов
    assert R.check_wr_mismatch(camp(own_total=2000, own_by_pl=own, ver={"shows": 2500, "by_placement": {1: 1250, 2: 1250}})).level == R.RED
    assert R.check_wr_mismatch(camp(own_total=2000, own_by_pl=own)).level == R.SKIP


def test_wr_mismatch_limit_comes_from_deal_goal():
    c = camp(goals={"weborama": "до 20 %"}, own_total=1000, own_by_pl={1: 1000},
             ver={"shows": 850, "by_placement": {1: 850}})
    assert R.check_wr_mismatch(c).level == R.GREEN                        # 15 % при пороге 20


def test_wr_outside_dsp_placement_is_not_compared():
    c = camp(own_total=1000, own_by_pl={1: 1000}, ver={"shows": 3400, "by_placement": {1: 1000, 2: 2400}})
    r = R.check_wr_mismatch(c)
    assert r.level == R.GREEN and r.value["wr"] == 1000                   # площадка 2 без нашего факта — мимо


def test_adfox_freshness():
    assert R.check_adfox_fresh(camp()).level == R.SKIP
    assert R.check_adfox_fresh(camp(adfox_last=AS_OF - timedelta(days=2))).level == R.YELLOW
    assert R.check_adfox_fresh(camp(adfox_last=AS_OF)).level == R.GREEN


# ── раскладка и темп ──
def test_shares_must_add_up():
    good = camp(placements=[pl(1, share=0.5, plan=500_000), pl(2, share=0.5, plan=500_000)])
    assert R.check_shares(good).level == R.GREEN
    bad = camp(placements=[pl(1, share=0.5, plan=500_000), pl(2, share=0.3, plan=300_000)])
    assert R.check_shares(bad).level == R.YELLOW


def test_pace_levels_and_too_early():
    assert R.check_pace(camp(own_total=330_000)).level == R.GREEN          # 10 дней из 31 → прогноз 1,02 млн
    assert R.check_pace(camp(own_total=290_000)).level == R.YELLOW
    assert R.check_pace(camp(own_total=200_000)).level == R.RED
    assert R.check_pace(camp(own_total=1, date_start=date(2026, 10, 9))).level == R.SKIP   # меньше трёх дней


# ── прогон целиком ──
def test_a_crashing_check_is_red_not_fatal(monkeypatch):
    def boom(_c):
        raise ValueError("x")
    monkeypatch.setitem(R.RUNNERS, "gaps", boom)
    res = R.run_checks(camp(placements=[pl(1)]))
    assert res["gaps"].level == R.RED and "не отработала" in res["gaps"].message
    assert set(res) == set(R.CHECKS)                                      # остальные отработали


def test_every_check_has_group_and_runner():
    assert set(R.RUNNERS) == set(R.CHECKS)
    groups = {g for g, _t in R.GROUPS}
    assert all(g in groups for g, _t in R.CHECKS.values())


def test_group_level_is_the_worst_of_its_checks():
    res = {k: R.Result(R.GREEN, "") for k in R.CHECKS}
    res["pixel"] = R.Result(R.RED, "")
    res["delivery"] = R.Result(R.YELLOW, "")
    lv = R.group_levels(res)
    assert lv == {"setup": R.RED, "collect": R.YELLOW, "layout": R.GREEN}


def test_skip_is_not_green_in_worst():
    assert R._worst([R.SKIP, R.SKIP]) == R.SKIP
    assert R._worst([R.SKIP, R.GREEN]) == R.GREEN


# ── «с какого дня» ──
def test_since_counts_unbroken_streak_only():
    h = [(date(2026, 10, d), "red") for d in (6, 7, 8, 9, 10)]
    assert since_of(h, "red") == "2026-10-06"
    broken = [(date(2026, 10, 5), "red"), (date(2026, 10, 7), "red"), (date(2026, 10, 8), "red")]
    assert since_of(broken, "red") == "2026-10-07"                        # 6-го прогона не было — серия прервана
    mixed = [(date(2026, 10, 7), "green"), (date(2026, 10, 8), "red"), (date(2026, 10, 9), "red")]
    assert since_of(mixed, "red") == "2026-10-08"
    assert since_of([], "red") is None


# ── на базе стенда ──
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.routers.auth import get_current_user  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


class _Role:
    def __init__(self, key):
        self.key, self.id = key, None


class _User:
    def __init__(self, key):
        self.id, self.name, self.email = None, "test", "t@t"
        self.role, self.role_id, self.consent_accepted_at = _Role(key), None, True


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _as(key):
    app.dependency_overrides[get_current_user] = lambda: _User(key)


def test_screen_needs_its_own_right(client):
    _as("sales")
    assert client.get("/api/rk-check").status_code == 403
    assert client.post("/api/rk-check/run").status_code == 403


def test_admin_overview_and_history_bounds(client):
    _as("admin")
    body = client.get("/api/rk-check").json()
    assert {"run_date", "summary", "groups", "campaigns"} <= set(body)
    assert client.get("/api/rk-check/1/history?days=0").status_code == 400
    assert client.get("/api/rk-check/999999/history").status_code == 404


def test_save_writes_campaign_rows_and_placement_rows_without_committing():
    db = SessionLocal()
    try:
        camps = R.load(db)
        if not camps:
            pytest.skip("на стенде нет идущих РК")
        out = R.save(db, camps, R.today_msk(), commit=False)
        assert out["campaigns"] == len(camps)
        n = db.execute(text("SELECT count(*) FROM rk_check_result WHERE run_date = :d AND placement_id IS NULL"),
                       {"d": R.today_msk()}).scalar()
        assert n == len(camps) * len(R.CHECKS)           # строка на проверку на РК, всегда
    finally:
        db.rollback()
        db.close()


# ── фазы РК, «площадки запущены», статистика по РК ──
def test_paused_campaign_expects_no_delivery():
    c = camp(status="пауза", placements=[pl(1)], dsp_days={1: days(1, 8)})
    res = R.run_checks(c)
    assert res["delivery"].level == R.SKIP and res["pace"].level == R.SKIP and res["gaps"].level == R.SKIP
    assert res["launch"].level == R.SKIP and "пауза" in res["launch"].message


def test_before_start_skips_collection_and_nudges_launch():
    c = camp(date_start=date(2026, 10, 12), today=date(2026, 10, 11), placements=[pl(1, status="ждёт сборки")])
    res = R.run_checks(c)
    assert {k: res[k].level for k in ("delivery", "gaps", "wr_mismatch", "pace", "fact_fresh")} == {
        k: R.SKIP for k in ("delivery", "gaps", "wr_mismatch", "pace", "fact_fresh")}
    assert res["launch"].level == R.YELLOW and "До старта 1 дн." in res["launch"].message
    far = camp(date_start=date(2026, 12, 1), today=date(2026, 10, 11), placements=[pl(1, status="ждёт сборки")])
    assert R.check_launch(far).level == R.SKIP


def test_running_flight_with_no_running_placement_is_red():
    r = R.check_launch(camp(placements=[pl(1, status="ждёт запуска"), pl(2, status="выключен")]))
    assert r.level == R.RED and "ни одна из 2" in r.message
    assert R.check_launch(camp(placements=[pl(1), pl(2, status="пауза")])).level == R.GREEN


def test_campaign_statistics_lag_is_read_per_campaign():
    live = dict(placements=[pl(1)], dsp_days={1: days()})
    assert R.check_fact_fresh(camp(last_stat=AS_OF, **live)).level == R.GREEN
    assert R.check_fact_fresh(camp(last_stat=AS_OF - timedelta(days=1), **live)).level == R.YELLOW
    r = R.check_fact_fresh(camp(last_stat=AS_OF - timedelta(days=2), **live))
    assert r.level == R.RED and "последние данные от 08.10" in r.message
    assert R.check_fact_fresh(camp(last_stat=None, **live)).level == R.RED
    assert R.check_fact_fresh(camp(last_stat=None, placements=[pl(1, status="ждёт сборки")])).level == R.GREEN


def test_no_plan_is_said_in_words():
    assert "Нет плана" in R.check_pace(camp(plan_show=None)).message
    assert "Нет плана" in R.check_shares(camp(plan_show=None, placements=[pl(1, share=1)])).message


# ── сводка и общие причины ──
def _chk(**lv):
    return [{"key": k, "level": v, "message": f"msg-{k}"} for k, v in lv.items()]


def test_common_cause_needs_three_campaigns():
    two = {1: {"adfox_fresh": R.YELLOW}, 2: {"adfox_fresh": R.YELLOW}, 3: {"adfox_fresh": R.GREEN}}
    assert R.common_keys(two) == {}
    three = {**two, 3: {"adfox_fresh": R.YELLOW}}
    assert R.common_keys(three) == {"adfox_fresh": 3}


def test_common_cause_does_not_raise_the_level():
    checks = _chk(pixel=R.GREEN, fact_fresh=R.RED, adfox_fresh=R.YELLOW, delivery=R.GREEN)
    s = R.build_summary(checks, {"fact_fresh": 5, "adfox_fresh": 5})
    assert s["worst"] == R.GREEN
    collect = next(g for g in s["groups"] if g["key"] == "collect")
    assert collect["level"] == R.GREEN and collect["action"] is None
    assert [p["common"] for p in collect["pips"] if p["key"] == "fact_fresh"] == [True]


def test_summary_text_and_action_come_from_the_worst_check():
    checks = _chk(pixel=R.YELLOW, erid=R.RED, dsp_campaign=R.GREEN, stage_sync=R.GREEN)
    s = R.build_summary(checks, {})
    setup = next(g for g in s["groups"] if g["key"] == "setup")
    assert setup["level"] == R.RED and setup["text"].startswith("msg-erid") and "ещё проверок: 1" in setup["text"]
    assert setup["action"]["target"] == "placements"
    assert (setup["ok"], setup["total"]) == (2, 4)
    assert s["worst"] == R.RED and not s["all_ok"]


def test_all_green_summary_is_all_ok():
    s = R.build_summary(_chk(pixel=R.GREEN, delivery=R.GREEN, pace=R.GREEN), {})
    assert s["all_ok"] and s["worst"] == R.GREEN
    assert [g["title"] for g in s["groups"]] == ["Заведение", "Сбор", "Раскладка"]


def test_dashboard_summary_needs_the_dashboard_right_and_has_the_contract(client):
    _as("nobody_role")
    assert client.get("/api/rk-check/summary").status_code == 403
    _as("admin")
    body = client.get("/api/rk-check/summary").json()
    assert {"run_date", "checked_at", "need_action", "common", "by_campaign"} <= set(body)
    for v in list(body["by_campaign"].values())[:3]:
        assert {"code", "worst", "all_ok", "groups"} <= set(v)
        assert [g["title"] for g in v["groups"]] == ["Заведение", "Сбор", "Раскладка"]
        assert all({"level", "text", "action", "ok", "total", "pips"} <= set(g) for g in v["groups"])


# ── готовые к запуску, но не включённые ──
def test_ready_but_not_started_placements_are_highlighted():
    c = camp(placements=[pl(1), pl(2, status="ждёт запуска"), pl(3, status="ждёт запуска")],
             ready=[{"id": 2, "name": "site2.ru"}, {"id": 3, "name": "site3.ru"}])
    r = R.check_ready_to_start(c)
    assert r.level == R.YELLOW and "2 из 3" in r.message and "site2.ru" in r.message
    assert [i.placement_id for i in r.items] == [2, 3]
    s = R.build_summary([{"key": "ready_to_start", "level": r.level, "message": r.message}], {})
    setup = next(g for g in s["groups"] if g["key"] == "setup")
    assert setup["action"] == {"label": "запустить готовые", "target": "start", "check": "ready_to_start"}


def test_nothing_ready_is_green_and_far_future_or_paused_is_not_nagged():
    assert R.check_ready_to_start(camp(placements=[pl(1)])).level == R.GREEN
    far = camp(date_start=date(2026, 12, 1), today=date(2026, 10, 11), placements=[pl(1, status="ждёт запуска")],
               ready=[{"id": 1, "name": "x.ru"}])
    assert R.check_ready_to_start(far).level == R.SKIP
    paused = camp(status="пауза", placements=[pl(1, status="ждёт запуска")], ready=[{"id": 1, "name": "x.ru"}])
    assert R.run_checks(paused)["ready_to_start"].level == R.SKIP


def test_ready_uses_the_same_start_rule_as_the_button():
    """Площадка с несогласованным или невыгруженным в DSP креативом не «готова», внешняя — тоже."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        camps = R.load(db)
        for c in camps:
            waiting = {p["id"] for p in c.placements if p["status"] == "ждёт запуска"}
            assert {p["id"] for p in c.ready} <= waiting
    finally:
        db.close()


def test_agreed_but_not_in_dsp_is_its_own_highlight():
    c = camp(placements=[pl(1), pl(2, status="ждёт запуска")], awaiting=[{"id": 2, "name": "site2.ru"}])
    r = R.check_awaiting_dsp(c)
    assert r.level == R.YELLOW and "не выгружены в DSP: 1" in r.message and r.items[0].placement_id == 2
    s = R.build_summary([{"key": "awaiting_dsp", "level": r.level, "message": r.message}], {})
    assert next(g for g in s["groups"] if g["key"] == "setup")["action"]["target"] == "dsp"
    assert R.check_awaiting_dsp(camp(placements=[pl(1)])).level == R.GREEN
    assert R.run_checks(camp(status="пауза", placements=[pl(1)], awaiting=[{"id": 1, "name": "x"}]))["awaiting_dsp"].level == R.SKIP
