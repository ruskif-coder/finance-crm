"""Контрактные smoke-тесты: форма ответов эндпойнтов, на которых висят
виджеты v2-страниц (реестр/дашборд/аналитика/дебиторка). Виджеты не типизированы —
переименование/пропажа поля ломает UI молча. Тесты фиксируют набор ключей.

Запуск: docker exec finance_backend python -m pytest tests/test_v2_contract.py -q
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import get_current_user


class _FakeRole:
    key = "admin"


class _FakeAdmin:
    id = 1
    name = "Contract Test"
    role = _FakeRole()


@pytest.fixture()
def client():
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _keys(d):
    return set(d.keys()) if isinstance(d, dict) else set()


def test_bonus_contract(client):
    r = client.get("/api/sales/dashboard/bonus")
    assert r.status_code == 200, r.text
    j = r.json()
    # используется SalesQuarterWidgets + подсветкой своей строки в аналитике
    for k in ("rep", "quarter", "linked", "can_view_others", "rep_ids", "params",
              "forming_bonus", "closed", "booking", "sandbox"):
        assert k in j, f"bonus: пропало поле {k}"
    assert _keys(j["params"]) >= {"bonus_rate", "agency_sk"}
    assert _keys(j["closed"]) >= {"amount", "our_sum"}
    assert _keys(j["booking"]) >= {"amount", "our_sum", "bonus", "by_stage"}
    assert _keys(j["sandbox"]) >= {"count", "amount"}
    assert isinstance(j["rep_ids"], list)


def test_dashboard_summary_contract(client):
    r = client.get("/api/sales/dashboard")
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("totals", "by_layer", "by_month", "by_sales_rep", "by_account_manager",
              "by_agency", "by_advertiser", "by_product", "by_pipeline", "last_sync_at"):
        assert k in j, f"dashboard: пропало поле {k}"
    assert _keys(j["totals"]) >= {"deals", "amount", "fact", "work", "deals_without_period", "reconciles"}
    # по слоям — то, что читают виджеты (сумма/кол-во/разбивка)
    if j["by_layer"]:
        assert _keys(j["by_layer"][0]) >= {"name", "amount", "deals", "fact", "real", "plan"}
    if j["by_month"]:
        assert _keys(j["by_month"][0]) >= {"name", "fact", "real", "plan", "deals"}
    if j["by_sales_rep"]:
        assert _keys(j["by_sales_rep"][0]) >= {"name", "fact", "real", "plan"}


def test_deals_row_contract(client):
    r = client.get("/api/sales/deals?limit=1")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "items" in j and "total" in j
    if j["items"]:
        row = j["items"][0]
        # поля, которые рендерит v2-таблица и инлайн-поповеры
        for k in ("id", "bitrix_id", "title", "agency", "advertiser", "brand", "product",
                  "period", "bitrix_stage", "amount", "account_manager", "payer",
                  "money_layer", "brief_state", "advertiser_id", "agency_id",
                  "sales_rep_id", "period_from", "period_to"):
            assert k in row, f"deal row: пропало поле {k}"


def test_filters_contract(client):
    r = client.get("/api/sales/filters")
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("advertiser_id", "agency_id", "sales_rep_id", "account_manager_id",
              "pipeline", "product", "bitrix_stage", "stage_key"):
        assert k in j, f"filters: пропал ключ {k}"
    for k in ("advertiser_id", "agency_id"):
        if j[k]:
            assert _keys(j[k][0]) >= {"value", "label"}, f"filters[{k}]: не {{value,label}}"


def test_receivables_contract(client):
    r = client.get("/api/reports/receivables")
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("as_of", "summary", "rows"):
        assert k in j, f"receivables: пропало поле {k}"
    assert isinstance(j["rows"], list)
    if j["rows"]:
        row = j["rows"][0]
        for k in ("counterparty", "counterparty_id", "inn", "note", "term_days",
                  "amount", "op_count", "aging", "operations"):
            assert k in row, f"receivables row: пропало поле {k}"
        assert _keys(row["aging"]) >= {"overdue", "current", "future", "unknown"}
        if row["operations"]:
            op = row["operations"][0]
            for k in ("id", "amount", "period", "due_date", "aging_bucket", "article"):
                assert k in op, f"receivables op: пропало поле {k}"
