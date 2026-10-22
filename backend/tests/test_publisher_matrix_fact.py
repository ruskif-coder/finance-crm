# -*- coding: utf-8 -*-
"""«Факт площадок» в матрице согласований (владелец 22.10.2026): факт и сумма — те же, что биллинг
в кабинете площадки (показы за вычетом Block SIMB × CPM договора / 1000, до НДС). Один источник —
`app.traffic.stats`, а не своя формула в матрице. Только чтение базы стенда."""
from collections import defaultdict

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.launch_prep import matrix as M
from app.traffic import stats


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _month_with_fact(db):
    row = db.execute(text("""
        SELECT to_char(d.period_from, 'YYYY-MM') FROM ad_campaign_stat s
          JOIN ad_campaign c ON c.id = s.campaign_id JOIN sales_deals d ON d.id = c.deal_id
         WHERE EXISTS (SELECT 1 FROM launch_prep_target t WHERE t.deal_id = d.id)
         GROUP BY 1 ORDER BY sum(s.shows) DESC LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет РК с фактом")
    return row[0]


def test_cells_carry_billing_fact_of_the_cabinet(db):
    month = _month_with_fact(db)
    got = M.load(db, month)
    deal_ids = {d["id"] for d in got["deals"]}
    want = defaultdict(int)
    for r in stats.compute(db, period=month)["rows"]:
        if r["deal_id"] in deal_ids:
            want[(r["deal_id"], r["publisher_id"])] += r["base"]
    cells = {(c["deal_id"], c["publisher_id"]): c for c in got["cells"]}
    assert any(c["fact_show"] for c in cells.values()), "в месяце с фактом матрица факта не показала"
    for key, c in cells.items():
        assert c["fact_show"] == want.get(key, 0), key


def test_fact_cost_is_fact_times_contract_cpm(db):
    got = M.load(db, _month_with_fact(db))
    cpm = {p["id"]: p["cpm"] for p in got["publishers"]}
    for c in got["cells"]:
        if not c["fact_show"]:
            assert c["fact_cost"] is None
        elif not cpm.get(c["publisher_id"]):
            assert c["fact_cost"] is None
        else:
            assert c["fact_cost"] == round(c["fact_show"] * cpm[c["publisher_id"]] / 1000, 2)
