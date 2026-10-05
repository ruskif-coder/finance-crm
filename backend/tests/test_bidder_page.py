# -*- coding: utf-8 -*-
"""Страница «Трафики → Биддер» (владелец 05.10.2026): правила, раскладка РК, журнал.

Право своё — `bidder` (view, edit), без бэкфилла: пока только владелец (админ).
Раскладка на странице — ТА ЖЕ функция, что ночной пересчёт (`build.campaign_layout`):
страница объясняет ровно то число, которое уходит в DSP.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.bidder.rules import RULES, explain
from app.database import SessionLocal
from app.main import app
from app.permissions import SECTIONS
from app.routers.auth import get_current_user


class _Role:
    def __init__(self, key):
        self.key = key
        self.id = None


class _User:
    def __init__(self, key):
        self.id, self.name, self.email = None, "test", "t@t"
        self.role = _Role(key)
        self.role_id = None
        self.consent_accepted_at = True


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _as(key):
    app.dependency_overrides[get_current_user] = lambda: _User(key)


def test_section_registered():
    sec = {s["key"]: s for s in SECTIONS}["bidder"]
    assert sec["group"] == "Трафики" and sec["actions"] == ["view", "edit"]


def test_rules_are_listed_with_dates():
    assert len(RULES) >= 5
    assert all(r["title"] and r["text"] and r["since"] for r in RULES)


def test_admin_sees_page(client):
    _as("admin")
    r = client.get("/api/bidder")
    assert r.status_code == 200
    body = r.json()
    assert body["rules"] and "cron" in body and "stale" in body


def test_others_do_not(client):
    _as("sales")
    assert client.get("/api/bidder").status_code == 403
    assert client.get("/api/bidder/campaigns").status_code == 403


def test_layout_adds_up(client):
    _as("admin")
    db = SessionLocal()
    cid = db.execute(text("SELECT id FROM ad_campaign WHERE plan_show > 0 ORDER BY id DESC LIMIT 1")).scalar()
    db.close()
    if cid is None:
        pytest.skip("на стенде нет РК с планом")
    r = client.get(f"/api/bidder/layout/{cid}")
    assert r.status_code == 200
    b = r.json()
    t = b["totals"]
    assert t["fixed"] + t["settled"] + t["by_weight"] == sum(x["plan_show"] or 0 for x in b["rows"])
    assert all(x["reason"] for x in b["rows"])


def test_layout_unknown_campaign_404(client):
    _as("admin")
    assert client.get("/api/bidder/layout/999999999").status_code == 404


@pytest.mark.parametrize("row,fact,want", [
    ({"in_plan": False, "settled": True, "plan_show": 500}, 500, "settled"),
    ({"in_plan": False, "settled": False, "plan_show": None}, 0, "out"),
    ({"in_plan": True, "fixed": 1000, "plan_show": 1000}, 0, "fixed"),
    ({"in_plan": True, "no_weight": True, "plan_show": None}, 0, "no_weight"),
    ({"in_plan": True, "plan_show": 4000}, 4000, "floored"),
    ({"in_plan": True, "plan_show": 500}, 10, "capped"),
    ({"in_plan": True, "plan_show": 300}, 10, "weight"),
])
def test_explain(row, fact, want):
    assert explain(row, fact, facts_used=True, cap_abs=500)["code"] == want


def test_campaigns_mark_running(client):
    _as("admin")
    rows = client.get("/api/bidder/campaigns").json()
    assert all("running" in r and r["running"] >= 0 for r in rows)
