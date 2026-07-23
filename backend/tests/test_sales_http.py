"""
HTTP-тесты реестра сделок.

Пишутся отдельно от остальных, потому что дважды за разработку ломался именно
слой между браузером и функцией, а не сама логика:

1. Вызов _base_query в реестре не получал bitrix_stage/brand_id/agency_id —
   фильтры молча не применялись. Прямой вызов функции этого не ловил.
2. Axios 1.x шлёт массивы как `money_layer[]=a&money_layer[]=b`, а FastAPI
   для List[...] ждёт повторяющийся ключ без скобок и параметры со скобками
   игнорирует — ни один чекбокс не срабатывал.

Оба случая проходили любые unit-тесты. Ловит их только запрос через ASGI.

Тесты идут в реальную БД контейнера, но только на чтение. Утверждения
относительные (подмножество, а не точные числа), чтобы не ломаться от данных.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import get_current_user


class _FakeRole:
    key = "admin"


class _FakeAdmin:
    """require_permission пропускает admin без обращения к role_permissions,
    поэтому подменяем только пользователя — сам гейт прав остаётся настоящим."""
    id = None
    name = "test"
    role = _FakeRole()


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _total(client, params=None):
    r = client.get("/api/sales/deals", params=params or {})
    assert r.status_code == 200, r.text
    return r.json()["total"]


def test_registry_responds(client):
    r = client.get("/api/sales/deals", params={"limit": 1})
    assert r.status_code == 200
    body = r.json()
    assert {"total", "items", "limit", "offset"} <= set(body)


def test_repeated_key_array_is_parsed(client):
    """Главный регресс: ?money_layer=a&money_layer=b должен фильтровать."""
    everything = _total(client)
    one = _total(client, {"money_layer": ["фактические"]})
    assert one < everything, "фильтр по слою не применился"


def test_two_values_widen_selection(client):
    one = _total(client, {"money_layer": ["фактические"]})
    two = _total(client, {"money_layer": ["фактические", "планируемые"]})
    assert two > one, "второе значение списка не учтено"


def test_bracket_style_array_is_ignored(client):
    """Документирует ловушку: axios по умолчанию шлёт именно такой формат,
    и FastAPI его не распознаёт. Если поведение изменится — тест упадёт,
    и это повод пересмотреть paramsSerializer во фронтенде."""
    everything = _total(client)
    bracketed = _total(client, {"money_layer[]": "фактические"})
    assert bracketed == everything


def test_stage_filter_applies(client):
    """Фильтр по стадии раньше не доходил до запроса вовсе."""
    everything = _total(client)
    filtered = _total(client, {"bitrix_stage": ["Архив"]})
    assert filtered < everything


def test_stage_and_layer_combine(client):
    only_stage = _total(client, {"bitrix_stage": ["Архив"]})
    combined = _total(client, {"bitrix_stage": ["Архив"], "money_layer": ["планируемые"]})
    assert combined <= only_stage


def test_gaps_filter_returns_subset(client):
    everything = _total(client)
    gaps = _total(client, {"gaps": ["sales_rep_id"]})
    assert gaps <= everything


def test_unknown_sort_field_rejected(client):
    r = client.get("/api/sales/deals", params={"sort": "нет такого поля"})
    assert r.status_code == 400


def test_bad_period_format_rejected(client):
    r = client.get("/api/sales/deals", params={"date_from": "2026"})
    assert r.status_code == 400


def test_filters_endpoint_lists_options(client):
    r = client.get("/api/sales/filters")
    assert r.status_code == 200
    body = r.json()
    for key in ("money_layer", "pipeline", "bitrix_stage",
                "advertiser_id", "brand_id", "agency_id",
                "sales_rep_id", "account_manager_id"):
        assert key in body, f"в /filters нет {key}"


def test_dashboard_reconciles(client):
    """Сумма по слоям обязана сходиться с общим итогом."""
    r = client.get("/api/sales/dashboard")
    assert r.status_code == 200
    assert r.json()["totals"]["reconciles"] is True


def test_sync_without_webhook_reports_unavailable(client):
    """Пока вебхук не настроен, синхронизация честно отвечает ошибкой,
    а не рисует пустой успешный прогон."""
    r = client.post("/api/sales/sync")
    assert r.status_code in (501, 503)
