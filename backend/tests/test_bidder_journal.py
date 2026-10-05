# -*- coding: utf-8 -*-
"""Журнал ночных прогонов биддера и «записанный» план на экранах (владелец 05.10.2026).

Экраны показывают план, записанный ночью (ровно то, что ушло лимитами в DSP), а не
пересчитанный на лету. Прогон пишет `bidder_run`, изменения планов — `bidder_run_change`.
Тест убирает только свои строки (id > max на старте).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ad.flight import distribute, flight_of
from app.database import SessionLocal

ON = "запущен"


def test_dashboard_row_shows_stored_plan():
    fl = flight_of(date(2026, 10, 1), date(2026, 10, 30), date(2026, 10, 10))
    pls = [{"id": 1, "status": ON, "weight": 1, "plan_stored": 7000, "share_stored": 0.7},
           {"id": 2, "status": ON, "weight": 1, "plan_stored": 3000, "share_stored": 0.3}]
    r = {x["id"]: x for x in distribute(10000, None, fl, pls, use_stored=True)["rows"]}
    assert r[1]["plan_show"] == 7000 and r[1]["share"] == 0.7
    assert r[2]["plan_show"] == 3000


def test_tables_exist():
    db = SessionLocal()
    try:
        got = {r[0] for r in db.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('bidder_run', 'bidder_run_change')")).all()}
    finally:
        db.close()
    assert got == {"bidder_run", "bidder_run_change"}


@pytest.fixture
def own_runs():
    db = SessionLocal()
    start = db.execute(text("SELECT coalesce(max(id), 0) FROM bidder_run")).scalar()
    db.close()
    yield start
    db = SessionLocal()
    db.execute(text("DELETE FROM bidder_run WHERE id > :s"), {"s": start})
    db.commit()
    db.close()


def test_run_is_journaled(own_runs):
    from app.ad import daily_shares
    out = daily_shares.run(campaign_ids=[])
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT finished_at, campaigns, by_fact FROM bidder_run "
                              "WHERE id > :s ORDER BY id DESC LIMIT 1"), {"s": own_runs}).first()
    finally:
        db.close()
    assert row is not None and row[0] is not None and row[1] == 0
    assert out["run_id"]


def test_dry_run_is_not_journaled(own_runs):
    from app.ad import daily_shares
    daily_shares.run(dry_run=True, campaign_ids=[])
    db = SessionLocal()
    try:
        n = db.execute(text("SELECT count(*) FROM bidder_run WHERE id > :s"), {"s": own_runs}).scalar()
    finally:
        db.close()
    assert n == 0


def test_plan_change_is_recorded(monkeypatch):
    from app.ad import build
    from tests.test_hold_distribution import _camp_with_placement
    monkeypatch.setattr(build, "deal_plan", lambda db_, d: {"surfaces": ["web"], "services": []})
    monkeypatch.setattr(build, "publisher_weights", lambda db_, s: {})
    db = SessionLocal()
    camp, pl, _pub = _camp_with_placement(db)
    try:
        db.execute(text("UPDATE ad_campaign_placement SET plan_show = 123 WHERE id = :i"), {"i": pl.id})
        db.commit()
        monkeypatch.setattr(build, "publisher_weights", lambda db_, s: {_pub: 1})
        out = build.refresh_weights(db, commit=False, campaign_ids=[camp.id])
        ch = [c for c in out["changes"] if c["placement_id"] == pl.id]
        assert ch and ch[0]["plan_before"] == 123 and ch[0]["plan_after"] == 1000
        assert ch[0]["reason"]
    finally:
        db.rollback()
        db.execute(text("DELETE FROM ad_campaign WHERE id = :i"), {"i": camp.id})
        db.commit()
        db.close()


def test_runs_endpoint_admin_only():
    from app.main import app
    from app.routers.auth import get_current_user
    from tests.test_bidder_page import _User
    with TestClient(app) as c:
        app.dependency_overrides[get_current_user] = lambda: _User("admin")
        assert c.get("/api/bidder/runs").status_code == 200
        app.dependency_overrides[get_current_user] = lambda: _User("sales")
        assert c.get("/api/bidder/runs").status_code == 403
    app.dependency_overrides.clear()


def test_journal_failure_never_blocks_recompute(monkeypatch):
    """Ревью 05.10.2026: нет таблицы журнала (бэкенд раньше миграции) — пересчёт и лимиты
    всё равно идут; журнал — справка, не условие работы."""
    from app.ad import daily_shares
    from app.bidder import journal

    def boom(*a, **k):
        raise RuntimeError("relation bidder_run does not exist")
    monkeypatch.setattr(journal, "start", boom)
    monkeypatch.setattr(journal, "finish", boom)
    out = daily_shares.run(campaign_ids=[])
    assert out["dry_run"] is False and out["run_id"] is None


def test_runs_in_moscow_time_and_state(own_runs):
    from app.bidder import journal
    db = SessionLocal()
    try:
        db.execute(text("INSERT INTO bidder_run (started_at) VALUES (now() AT TIME ZONE 'UTC')"))
        db.commit()
        r = [x for x in journal.runs(db) if x["id"] > own_runs][0]
    finally:
        db.close()
    assert r["state"] == "идёт", "свежий незакрытый прогон — идёт, а не оборвался"
    assert r["started_msk"] and len(r["started_msk"]) == 16
