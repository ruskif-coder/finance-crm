# -*- coding: utf-8 -*-
"""Ночной забор Adfox через API (владелец 11.11.2026): из API — ТОЛЬКО показы («клики не трогать»: у API commercial-клики
24 за день против 3 146 переходов ручного отчёта), сопоставление — тем же разбором, что «↑ ADFOX»; день размещения,
где в отчёте есть несопоставленная строка с этим размещением среди вариантов, не пишется; на размещение с фактом DSP — не пишем."""
from datetime import date

import httpx

from app.adfox import stats as S
from app.adfox.client import AdfoxClient

D = date(2026, 11, 7)


def test_v2_report_posts_level_and_date_range_and_returns_dict_rows():
    seen = []

    def h(req):
        seen.append(req)
        if req.method == "POST":
            return httpx.Response(200, json={"result": {"taskId": "T", "status": "PENDING"}})
        if req.url.path.endswith("/result"):
            return httpx.Response(200, json={"result": {"columns": [{"name": "campaign_name"}, {"name": "impressions_commercial"}],
                                                        "rows": [["UQTXRV-MXV-cr2-01_AK\r\n", 20543]]}})
        return httpx.Response(200, json={"result": {"status": "SUCCESS"}})
    cl = AdfoxClient(token="t", http=httpx.Client(transport=httpx.MockTransport(h)))
    rows = cl.report_v2("campaigns", "owner", "2026-11-07", "2026-11-07", sleep=lambda s: None)
    assert rows == [{"campaign_name": "UQTXRV-MXV-cr2-01_AK\r\n", "impressions_commercial": 20543}]
    import json
    assert seen[0].url.path == "/api/v2/reports/campaigns"
    assert json.loads(seen[0].content) == {"level": "owner", "dateRange": {"from": "2026-11-07", "to": "2026-11-07"}}


def test_api_rows_become_import_rows_with_clean_name_and_shows():
    out = S.to_rows([{"campaign_name": "UQTXRV-MXV-cr2-01_AK\r\n", "impressions_commercial": 20543, "clicks_commercial": 3}], D)
    assert out == [{"line": 1, "day": D, "name": "UQTXRV-MXV-cr2-01_AK", "shows": 20543, "clicks": None, "uniques": None}]


def _m(pl, cr, shows, camp=1):
    return {"status": "matched", "placement_id": pl, "creative_id": cr, "campaign_id": camp, "day": D, "shows": shows, "line": 1}


def test_select_skips_dsp_placements_and_days_touched_by_unresolved_rows():
    rs = [_m(10, 100, 500), _m(11, 110, 300), _m(12, 120, 200),
          {"status": "ambiguous", "day": D, "candidates": [{"placement_id": 11}], "line": 9}]
    agg, skipped = S.select(rs, dsp_placements={12})
    assert sorted(k[1] for k in agg) == [10]
    assert agg[(1, 10, D)]["shows"] == 500 and agg[(1, 10, D)]["creatives"] == {100: 500}
    assert sorted(skipped) == [(11, "в отчёте есть несопоставленная строка, которая может быть этим размещением"),
                               (12, "размещение крутится в DSP — факт оттуда")]


def test_write_updates_shows_only_and_keeps_manual_clicks_and_uniques():
    """На живом стенде в откатываемой транзакции: строка ручной загрузки с кликами и уникальными — показы меняются, остальное нет."""
    import pytest
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        r = db.execute(text("""SELECT campaign_id, placement_id, date, shows, clicks, uniques FROM ad_campaign_stat
                                WHERE source = 'adfox' AND clicks > 0 AND uniques IS NOT NULL LIMIT 1""")).first()
        if r is None:
            pytest.skip("на стенде нет ручной загрузки Adfox с кликами")
        S.write(db, {(r.campaign_id, r.placement_id, r.date): {"shows": r.shows + 7, "creatives": {}}})
        got = db.execute(text("""SELECT shows, clicks, uniques FROM ad_campaign_stat WHERE source = 'adfox'
                                  AND placement_id = :p AND date = :d"""), {"p": r.placement_id, "d": r.date}).first()
        assert (got.shows, got.clicks, got.uniques) == (r.shows + 7, r.clicks, r.uniques)
    finally:
        db.rollback()
        db.close()
