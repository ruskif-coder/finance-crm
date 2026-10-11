# -*- coding: utf-8 -*-
"""«Разбор РК» (11.10.2026): сервер отдаёт данные в мелком зерне, правила — общие с остальной системой.
Проверяем права (как у дашборда трафика), ответы на кривой ввод, состав ответа на живой РК стенда,
выгрузку среза и то, что уники модели те же, что в отчёте клиенту."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ad import rk_analysis as A
from app.database import SessionLocal
from app.main import app
from app.routers.auth import get_current_user


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


@pytest.fixture
def code():
    db = SessionLocal()
    try:
        c = db.execute(text("""SELECT d.code FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
                               WHERE EXISTS (SELECT 1 FROM ad_campaign_stat s WHERE s.campaign_id = c.id AND s.source = 'dsp')
                               ORDER BY c.id LIMIT 1""")).scalar()
    finally:
        db.close()
    if not c:
        pytest.skip("на стенде нет РК с фактом DSP")
    return c


def test_needs_the_dashboard_right(client, code):
    _as("nobody_role")
    assert client.get(f"/api/rk-analysis/{code}").status_code == 403
    assert client.post(f"/api/rk-analysis/{code}/export.xlsx", json={"title": "x", "columns": [{"key": "a", "label": "A"}], "rows": []}).status_code == 403


def test_bad_and_unknown_codes_answer_4xx(client):
    _as("admin")
    assert client.get("/api/rk-analysis/..%2Fetc").status_code in (400, 404)
    assert client.get("/api/rk-analysis/ZZZZZZ").status_code == 404


def test_payload_is_fine_grained_and_cut_at_the_fact_date(client, code):
    _as("admin")
    d = client.get(f"/api/rk-analysis/{code}").json()
    assert {"head", "placements", "stat", "model_uniques", "creative_days", "events", "checks", "prev"} <= set(d)
    as_of = d["head"]["as_of"]
    assert all(r["date"] <= as_of for r in d["stat"])
    assert {r["source"] for r in d["stat"]} <= {"dsp", "adfox", "weborama"}
    pids = {p["id"] for p in d["placements"]}
    assert all(r["placement_id"] in pids for r in d["stat"])
    assert d["head"]["wr_limit"] > 0
    # события площадок привязаны к площадке этой РК
    for e in d["events"]:
        assert e["kind"] in {"start", "pause", "campaign", "bidder", "boost", "tech"}
        if e["placement_id"] is not None:
            assert e["placement_id"] in pids


def test_prev_options_are_earlier_same_brand_campaigns_with_fact():
    db = SessionLocal()
    try:
        row = db.execute(text("""SELECT d.code FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
                                 WHERE d.advertiser_id IS NOT NULL AND c.date_start IS NOT NULL ORDER BY c.date_start DESC LIMIT 1""")).scalar()
        if not row:
            pytest.skip("нет РК с рекламодателем")
        head = A.head_of(db, row)
        for o in A.prev_options(db, head):
            assert o["campaign_id"] != head["id"]
            assert o["date_start"] < str(head["date_start"])
    finally:
        db.close()


def test_model_uniques_match_the_client_report(code):
    """Уники на странице — из той же функции, что «Отчёт клиенту с поправкой»: сумма по РК совпадает."""
    from app.ad import client_report
    from app.dsp.db import DspSessionLocal
    db, ddb = SessionLocal(), (DspSessionLocal() if DspSessionLocal else None)
    try:
        head = A.head_of(db, code)
        as_of = date.fromisoformat(str(A.build(db, head, dsp_db=ddb)["head"]["as_of"]))
        pls = A.placements_of(db, head["id"])
        page = sum(x["uniques"] for x in A.model_uniques_of(db, ddb, head, pls, as_of))
        rep = client_report.build(db, head["id"], date_from=head["date_start"], date_to=as_of, dsp_db=ddb, model=True)
        doms = {p["domain"] for p in pls}
        excel = round(sum(v[2] for site, days in rep.site_days.items() if site in doms for v in days.values()))
        assert abs(page - excel) <= len(pls) * 31     # округление по дням
    finally:
        db.rollback(); db.close()
        if ddb is not None:
            ddb.close()


def test_export_returns_xlsx_and_limits_input(client, code):
    _as("admin")
    ok = client.post(f"/api/rk-analysis/{code}/export.xlsx",
                     json={"title": "Срез", "columns": [{"key": "label", "label": "День"}, {"key": "fact", "label": "Факт"}],
                           "rows": [{"label": "01.10", "fact": 10}, {"label": "=HYPERLINK(\"x\")", "fact": 1}]})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/vnd.openxmlformats")
    too_many = client.post(f"/api/rk-analysis/{code}/export.xlsx",
                           json={"title": "x", "columns": [{"key": f"c{i}", "label": "c"} for i in range(A.MAX_COLS + 1)], "rows": []})
    assert too_many.status_code == 400
