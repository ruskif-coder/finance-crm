# -*- coding: utf-8 -*-
"""Полоса итогов и плитки-фильтры «Операций» (хендофф design_handoff_operations_navy, 17.11.2026).

Поломки, которые ловит набор:
- итоги считаются не по фильтру (по странице или по всей базе) — плитки расходятся с таблицей;
- «Просроченная ДЗ» в SQL расходится с правилом старения `_receivable_status` (receivables.py) — точка ДЗ красная, а в плитке нет;
- плитка «Незаполненные» не видит контрагента-заглушку «ПЛАН»;
- `quick` фильтрует не то: «поступления» с расходами, «просроченные» с оплаченными.
Только чтение данных стенда."""
import pytest
from fastapi.testclient import TestClient

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.main import app
from app.models import Operation, User
from app.routers.auth import create_access_token, token_claims
from app.routers.operations import PLAN_COUNTERPARTY, _receivable_status


@pytest.fixture(scope="module")
def client():
    db = SessionLocal()
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    tok = create_access_token(token_claims(u))
    db.close()
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


@pytest.fixture(scope="module")
def ops():
    db = SessionLocal()
    rows = db.query(Operation).all()
    data = [(o.status, o.income or 0, o.expense or 0, _receivable_status(o),
             o.counterparty is None or o.counterparty.name == PLAN_COUNTERPARTY, o.article_id is None) for o in rows]
    db.close()
    if not data:
        pytest.skip("на стенде нет операций")
    return data


def test_summary_matches_python_over_the_same_rows(client, ops):
    s = client.get("/api/operations/summary").json()
    paid = [o for o in ops if o[0] == "ОПЛАЧЕНО"]
    assert s["income_fact"] == pytest.approx(sum(o[1] for o in paid), abs=0.01)
    assert s["expense_plan"] == pytest.approx(sum(o[2] for o in ops if o[0] != "ОПЛАЧЕНО"), abs=0.01)
    over = [o for o in ops if o[3] == "overdue"]
    assert s["overdue_count"] == len(over)
    assert s["overdue_sum"] == pytest.approx(sum(o[1] for o in over), abs=0.01)
    assert s["empty_count"] == sum(1 for o in ops if o[4] or o[5])


def test_summary_follows_the_table_filter(client, ops):
    s = client.get("/api/operations/summary", params={"status": ["ПЛАН ОПЛАТ"]}).json()
    assert s["income_fact"] == 0 and s["expense_fact"] == 0          # оплаченных под этим фильтром нет
    assert s["expense_plan"] == pytest.approx(sum(o[2] for o in ops if o[0] == "ПЛАН ОПЛАТ"), abs=0.01)


@pytest.mark.parametrize("quick, keep", [
    ("in", lambda o: o[1] > 0), ("out", lambda o: o[2] > 0),
    ("over", lambda o: o[3] == "overdue"), ("empty", lambda o: o[4] or o[5]),
])
def test_quick_filter_counts(client, ops, quick, keep):
    r = client.get("/api/operations/", params={"quick": quick, "limit": 1}).json()
    assert r["total"] == sum(1 for o in ops if keep(o))


def test_export_follows_the_tile(client):
    """Выгрузка — тем же фильтром, что список (до 17.11.2026 у неё была своя копия цепочки и плитки она не знала)."""
    from io import BytesIO

    from openpyxl import load_workbook
    total = client.get("/api/operations/", params={"quick": "over", "limit": 1}).json()["total"]
    r = client.get("/api/operations/export", params={"quick": "over"})
    assert r.status_code == 200
    ws = load_workbook(BytesIO(r.content)).active
    rows = [row for row in ws.iter_rows(min_row=2, values_only=True) if any(v not in (None, "") for v in row)]
    assert len(rows) == total
