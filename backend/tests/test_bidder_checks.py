# -*- coding: utf-8 -*-
"""Проверки ночного прогона биддера и разбор изменений — в журнал (владелец 06.10.2026:
«мне бы эти статусы и возможные ошибки в лог биддера»). Тревога — владельцу, мастеру
трафика и «Админ Трафик», только на переходе «нормально → плохо»."""
from datetime import date

from app.bidder import checks as K

D = date(2026, 10, 6)


def _camp(**kw):
    base = {"id": 1, "code": "AAA111", "plan_show": 1000, "date_start": date(2026, 10, 1),
            "date_end": date(2026, 10, 31), "status": "запущена", "in_dsp": True, "creatives": 2,
            "plans": [500, 500], "facts": [100, 100]}
    return {**base, **kw}


def _codes(checks):
    return {c["code"]: c for c in checks}


def test_clean_run_is_ok():
    ch = K.evaluate([_camp()], by_fact=True, slice_vs_raw=(10, 10), limit_errors=[], today=D)
    assert ch == [] and K.state_of(ch) == "ок"


def test_rounding_is_not_a_mismatch():
    ch = K.evaluate([_camp(plans=[334, 334, 334])], by_fact=True, slice_vs_raw=(1, 1),
                    limit_errors=[], today=D)
    assert "sum_mismatch" not in _codes(ch)


def test_sum_mismatch_is_error():
    ch = _codes(K.evaluate([_camp(plans=[500, 700])], True, (1, 1), [], D))
    assert ch["sum_mismatch"]["level"] == "error" and ch["sum_mismatch"]["examples"][0].startswith("AAA111")


def test_unassigned_plan_is_warning_not_error():
    """6KZUTN 06.10.2026: одна площадка с заданным объёмом на треть плана — не перекрут."""
    ch = _codes(K.evaluate([_camp(plans=[333, None], facts=[0, 0])], True, (1, 1), [], D))
    assert "sum_mismatch" not in ch and ch["plan_unassigned"]["level"] == "warning"


def test_plan_below_fact_is_error():
    ch = _codes(K.evaluate([_camp(plans=[900, 100], facts=[0, 300])], True, (1, 1), [], D))
    assert ch["below_fact"]["level"] == "error" and ch["below_fact"]["count"] == 1


def test_campaign_without_layout_after_hold_is_warning_with_why():
    c = _camp(code="9HT4V9", plans=[None, None], facts=[0, 0], in_dsp=False, creatives=0,
              status="ожидает сборки")
    ch = _codes(K.evaluate([c], True, (1, 1), [], D))
    w = ch["no_layout"]
    assert w["level"] == "warning" and "9HT4V9" in w["examples"][0]
    assert "не выгружена в DSP" in w["examples"][0] and "нет креативов" in w["examples"][0]


def test_no_layout_during_hold_is_fine():
    c = _camp(date_start=date(2026, 10, 3), plans=[None], facts=[0])
    assert "no_layout" not in _codes(K.evaluate([c], True, (1, 1), [], D))


def test_stale_stats_is_warning():
    assert _codes(K.evaluate([], False, (1, 1), [], D))["stale"]["level"] == "warning"


def test_slice_not_matching_dsp_raw_is_error():
    ch = _codes(K.evaluate([], True, (736393, 736000), [], D))
    assert ch["slice_vs_raw"]["level"] == "error"


def test_limit_errors_are_listed_with_text():
    ch = _codes(K.evaluate([], True, (1, 1), [{"creative_id": 5, "error": "DSP: 2051"}], D))
    assert ch["limits_failed"]["level"] == "error" and "2051" in ch["limits_failed"]["examples"][0]


def test_state_and_alert_transition():
    warn = [{"level": "warning", "code": "stale"}]
    err = [{"level": "error", "code": "below_fact"}]
    assert K.state_of(warn) == "предупреждения" and K.state_of(err) == "ошибки"
    assert K.should_alert("ок", "ошибки") and K.should_alert(None, "предупреждения")
    assert not K.should_alert("ошибки", "ошибки"), "каждую ночь одно и то же — не спам"
    assert not K.should_alert("ошибки", "ок")


def test_reasons_summary_names_hold_end():
    changes = [{"campaign_id": 1, "reason": "out"}, {"campaign_id": 1, "reason": "weight"},
               {"campaign_id": 1, "reason": "weight"}, {"campaign_id": 2, "reason": "settled"}]
    starts = {1: date(2026, 10, 1), 2: date(2026, 9, 1)}
    s = K.summarize(changes, starts, D)
    assert any("удержание" in x and "1 РК" in x for x in s)
    assert any("вне раскладки" in x and "1" in x for x in s)
    assert any("план = факт" in x for x in s)


def test_alert_event_goes_to_admin_and_traffic_masters():
    from app.notify import registry
    ev = registry.get("cron_bidder_failed")
    assert {"type": "role", "value": "admin"} in ev.recipients
    assert {"type": "resolver", "value": "traffic_masters"} in ev.recipients
    assert ev.channels.get("tg") and ev.channels.get("mail") and ev.locked


def test_traffic_masters_are_master_roles_of_traffic():
    from app.database import SessionLocal
    from app.models import Role, User
    from app.notify.recipients import RESOLVERS
    db = SessionLocal()
    try:
        got = set(RESOLVERS["traffic_masters"](db, {}))
        want = {u.id for u in db.query(User).join(Role, Role.id == User.role_id)
                .filter(Role.staff_group == "traffic", Role.is_master.is_(True),
                        User.is_active == 1).all()}
    finally:
        db.close()
    assert got == want


def test_status_page_shows_bidder_checks(monkeypatch):
    from app.bidder import journal
    from app.system import status as S
    from datetime import datetime, timedelta
    now_msk = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
    run = {"started_msk": now_msk, "state": "ошибки",
           "checks": [{"level": "error", "title": "План площадки меньше уже открученного", "count": 2}]}
    monkeypatch.setattr(journal, "runs", lambda db, limit=60: [run])
    row = S.check_bidder(None)
    assert row["tone"] == "bad" and "открученного" in str(row)
    monkeypatch.setattr(journal, "runs", lambda db, limit=60: [{**run, "state": "ок", "checks": []}])
    assert S.check_bidder(None)["tone"] == "ok"


def test_nightly_writes_checks(monkeypatch):
    """Прогон пишет проверки в журнал и не падает, если проверка сама упала."""
    from sqlalchemy import text
    from app.ad import daily_shares
    from app.bidder import checks as K
    from app.database import SessionLocal
    db = SessionLocal()
    start = db.execute(text("SELECT coalesce(max(id), 0) FROM bidder_run")).scalar()
    db.close()
    monkeypatch.setattr(K, "gather", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    sent = []
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda db, ev, **kw: sent.append(ev))
    try:
        monkeypatch.setattr(daily_shares, "_SCOPE_ALL", lambda ids: True)
        out = daily_shares.run(campaign_ids=[])
        assert out["checks"][0]["code"] == "checks_failed"
        db = SessionLocal()
        got = db.execute(text("SELECT checks FROM bidder_run WHERE id = :i"), {"i": out["run_id"]}).scalar()
        db.close()
        assert got and got[0]["code"] == "checks_failed"
    finally:
        db = SessionLocal()
        db.execute(text("DELETE FROM bidder_run WHERE id > :s"), {"s": start})
        db.commit()
        db.close()


# ── ревью 06.10.2026 ─────────────────────────────────────────────────────────

def test_finished_flight_is_not_checked_for_fact_or_sum():
    """Флайт кончился, РК не закрыта, DSP чуть перекрутил — не ошибка каждую ночь."""
    c = _camp(date_start=date(2026, 9, 1), date_end=date(2026, 9, 30), plans=[500, 500],
              facts=[512, 500])
    assert K.evaluate([c], True, (1, 1), [], D) == []


def test_placement_out_of_layout_with_fact_is_not_below_fact():
    """Вне раскладки (плана нет) — проверка «план ниже факта» её не касается."""
    c = _camp(plans=[1000, None], facts=[100, 300])
    assert "below_fact" not in _codes(K.evaluate([c], True, (1, 1), [], D))


def test_slice_check_skipped_when_no_fresh_stats():
    ch = _codes(K.evaluate([], False, (0, 5000), [], D))
    assert "slice_vs_raw" not in ch and "stale" in ch


def test_state_by_level_not_by_word_in_example():
    """Слово error в примере не делает прогон «ошибками» (ревью 06.10.2026)."""
    from app.bidder import journal
    from app.database import SessionLocal
    from sqlalchemy import text
    import json
    db = SessionLocal()
    start = db.execute(text("SELECT coalesce(max(id), 0) FROM bidder_run")).scalar()
    try:
        db.execute(text("INSERT INTO bidder_run (started_at, finished_at, checks) VALUES "
                        "(now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', CAST(:c AS jsonb))"),
                   {"c": json.dumps([{"level": "warning", "code": "x", "title": "t", "count": 1,
                                      "examples": ["error"]}])})
        db.commit()
        r = [x for x in journal.runs(db) if x["id"] > start][0]
        assert r["state"] == "предупреждения"
        assert journal.run(db, r["id"])["state"] == "предупреждения"
    finally:
        db.execute(text("DELETE FROM bidder_run WHERE id > :s"), {"s": start})
        db.commit()
        db.close()


def test_scoped_run_does_not_check_or_alert(monkeypatch):
    """Ручной прогон по одной РК не проверяет и не тревожит по всем остальным."""
    from sqlalchemy import text
    from app.ad import daily_shares
    from app.bidder import checks as Kc
    from app.database import SessionLocal
    db = SessionLocal()
    start = db.execute(text("SELECT coalesce(max(id), 0) FROM bidder_run")).scalar()
    db.close()
    monkeypatch.setattr(Kc, "gather", lambda *a, **k: (_ for _ in ()).throw(AssertionError("gather")))
    try:
        out = daily_shares.run(campaign_ids=[999999999])
        assert out["checks"] == []
    finally:
        db = SessionLocal()
        db.execute(text("DELETE FROM bidder_run WHERE id > :s"), {"s": start})
        db.commit()
        db.close()
