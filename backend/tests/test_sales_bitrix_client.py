"""
Тесты клиента Битрикс24.

Проверяется пагинация (портал отдаёт по 50 записей и поле "next"),
обработка ошибки портала (приходит с HTTP 200, поэтому raise_for_status
её не ловит) и стабильность хеша полезной нагрузки — на нём держится
append-only слой сырья.
"""
import httpx
import pytest
from app.sales.bitrix_client import BitrixClient, payload_hash

WEBHOOK = "https://portal.bitrix24.ru/rest/1/token123/"


def _client_with(handler):
    transport = httpx.MockTransport(handler)
    return BitrixClient(WEBHOOK, client=httpx.Client(transport=transport))


def test_single_page_returns_all_items():
    def handler(request):
        return httpx.Response(200, json={"result": [{"ID": "1"}, {"ID": "2"}], "total": 2})

    items = _client_with(handler).list_entities("crm.deal.list")
    assert [i["ID"] for i in items] == ["1", "2"]


def test_pagination_follows_next_until_exhausted():
    pages = {
        0: {"result": [{"ID": "1"}], "next": 50, "total": 2},
        50: {"result": [{"ID": "2"}], "total": 2},
    }

    def handler(request):
        start = int(dict(request.url.params).get("start", 0))
        return httpx.Response(200, json=pages[start])

    items = _client_with(handler).list_entities("crm.deal.list")
    assert [i["ID"] for i in items] == ["1", "2"]


def test_method_is_appended_to_webhook_url():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"result": []})

    _client_with(handler).list_entities("crm.company.list")
    assert seen["path"].endswith("/crm.company.list")


def test_portal_error_raises_with_description():
    def handler(request):
        return httpx.Response(200, json={"error": "QUERY_LIMIT_EXCEEDED",
                                         "error_description": "Слишком много запросов"})

    with pytest.raises(RuntimeError) as exc:
        _client_with(handler).list_entities("crm.deal.list")
    assert "Слишком много запросов" in str(exc.value)


def test_http_error_raises():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        _client_with(handler).list_entities("crm.deal.list")


def test_empty_result_returns_empty_list():
    def handler(request):
        return httpx.Response(200, json={"result": []})

    assert _client_with(handler).list_entities("crm.deal.list") == []


def test_missing_webhook_url_raises():
    with pytest.raises(RuntimeError):
        BitrixClient("")


def test_payload_hash_is_stable_regardless_of_key_order():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})


def test_payload_hash_changes_when_value_changes():
    assert payload_hash({"amount": "100"}) != payload_hash({"amount": "101"})
