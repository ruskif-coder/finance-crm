import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.routers.auth import get_current_user
import app.routers.sales_reconcile as rec


class _FakeRole:
    key = "admin"


class _FakeAdmin:
    id = None
    name = "test"
    role = _FakeRole()


@pytest.fixture
def client(monkeypatch):
    # компании Битрикса не дёргаем живьём
    monkeypatch.setattr(rec, "_fetch_companies",
                        lambda kind, refresh=False: [{"id": "99999", "title": "ZZZ Fake Co"}])
    monkeypatch.setattr(rec, "_deal_counts_map", lambda refresh=False: {"99999": 7})
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_buckets_shape(client):
    r = client.get("/api/sales/reconcile/agencies")
    assert r.status_code == 200
    body = r.json()
    for key in ("linked", "candidates", "only_ours", "only_bitrix", "all_bitrix"):
        assert key in body
    assert {"id": "99999", "title": "ZZZ Fake Co"} in body["all_bitrix"]


def test_unknown_kind_rejected(client):
    r = client.get("/api/sales/reconcile/widgets")
    assert r.status_code == 400
