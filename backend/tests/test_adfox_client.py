# -*- coding: utf-8 -*-
"""Клиент API Adfox (v2) на подставном транспорте: опрос задачи до готовности; отказ доступа и ошибка — понятным текстом."""
import httpx
import pytest

from app.adfox.client import AdfoxClient, AdfoxError


def _client(handler):
    return AdfoxClient(token="t", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_report_polls_until_success_and_sends_oauth():
    seen, states = [], iter(["PENDING", "STARTED", "SUCCESS"])

    def h(req):
        seen.append(req)
        if req.method == "POST":
            return httpx.Response(200, json={"result": {"taskId": "T1", "status": "PENDING"}})
        if req.url.path.endswith("/result"):
            return httpx.Response(200, json={"result": {"columns": [{"name": "date"}], "rows": [["2026-11-10"]]}})
        return httpx.Response(200, json={"result": {"status": next(states)}})
    assert _client(h).report_v2("days", "owner", "2026-11-10", "2026-11-10", sleep=lambda s: None) == [{"date": "2026-11-10"}]
    assert seen[0].headers["Authorization"] == "OAuth t"
    assert len(seen) == 5, "задача + три опроса + результат"


def test_failed_report_is_an_error():
    def h(req):
        if req.method == "POST":
            return httpx.Response(200, json={"result": {"taskId": "T1"}})
        return httpx.Response(200, json={"result": {"status": "FAILURE"}})
    with pytest.raises(AdfoxError, match="FAILURE"):
        _client(h).report_v2("days", "owner", "2026-11-10", "2026-11-10", sleep=lambda s: None)


def test_forbidden_is_a_readable_error():
    with pytest.raises(AdfoxError, match="доступ"):
        _client(lambda req: httpx.Response(403, text="no")).reports()


def test_error_in_body_is_raised_with_its_message():
    with pytest.raises(AdfoxError, match="level is required"):
        _client(lambda req: httpx.Response(400, json={"error": {"code": "INVALID_REQUEST", "message": "level is required"}})).reports()


def test_without_token_the_client_refuses(monkeypatch):
    monkeypatch.delenv("ADFOX_OAUTH_TOKEN", raising=False)
    with pytest.raises(AdfoxError, match="не задан"):
        AdfoxClient()


def test_non_object_json_is_a_readable_error_not_a_crash():
    """Ревью 11.11.2026: ответ-список ронял клиент AttributeError — крон падал без понятной причины."""
    import httpx
    import pytest
    from app.adfox.client import AdfoxClient, AdfoxError
    cl = AdfoxClient(token="t", http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[1, 2]))))
    with pytest.raises(AdfoxError):
        cl.reports()
