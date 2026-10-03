# -*- coding: utf-8 -*-
"""Админ-кабинет DSP («пропали из показов») — внутри модуля DSP, а не в мониторе сайтов.

Аудит интеграций 02.10.2026: `traffic/site_monitor.py` держал второй, самописный клиент
DSP — свой вход, свои переменные, ошибка с адресом и телом ответа наружу. Теперь он в
`app/dsp/admin.py`, ошибки чистятся тем же правилом, что у основного клиента.
"""
import inspect

import httpx
import pytest

from app.dsp import admin


def test_site_monitor_has_no_own_dsp_client():
    from app.traffic import site_monitor as sm
    src = inspect.getsource(sm)
    assert "_dsp_rpc" not in src and "user.auth" not in src
    assert "platform.getStatistics" not in src


def test_configured_reads_one_place(monkeypatch):
    for k in admin.ENV + (admin.TOKEN_ENV,):
        monkeypatch.delenv(k, raising=False)
    assert not admin.configured()
    monkeypatch.setenv("DSP_ADMIN_API_URL", "https://dsp.example/api")
    assert not admin.configured()
    monkeypatch.setenv(admin.TOKEN_ENV, "t")
    assert admin.configured()


def test_error_does_not_leak_address_or_body(monkeypatch):
    monkeypatch.setenv("DSP_ADMIN_API_URL", "https://secret-vendor.example/api")
    monkeypatch.setenv(admin.TOKEN_ENV, "tok")
    monkeypatch.delenv("DSP_ADMIN_LOGIN", raising=False)
    monkeypatch.delenv("DSP_ADMIN_PASSWORD", raising=False)

    def handler(request):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2,
                                         "error": {"message": "boom https://secret-vendor.example/x"}})
    with pytest.raises(admin.AdminError) as e:
        admin.sites_with_shows(__import__("datetime").date(2026, 10, 1),
                               transport=httpx.MockTransport(handler))
    assert "secret-vendor" not in str(e.value)


def test_sites_with_shows_counts_only_positive(monkeypatch):
    monkeypatch.setenv("DSP_ADMIN_API_URL", "https://dsp.example/api")
    monkeypatch.setenv(admin.TOKEN_ENV, "tok")
    monkeypatch.delenv("DSP_ADMIN_LOGIN", raising=False)     # вход — токеном
    monkeypatch.delenv("DSP_ADMIN_PASSWORD", raising=False)

    def handler(request):
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": [
            {"site": "a.ru", "shows": "5"}, {"site": "b.ru", "shows": 0}, {"site": "c.ru", "shows": "x"}]})
    got = admin.sites_with_shows(__import__("datetime").date(2026, 10, 1),
                                 transport=httpx.MockTransport(handler))
    assert got == {"a.ru"}


def test_block_shows_missing_block_is_zero(monkeypatch):
    """Админка отдаёт только блоки с показами: спрошенный и не пришедший — ноль."""
    monkeypatch.setenv("DSP_ADMIN_API_URL", "https://dsp.example/api")
    monkeypatch.setenv("DSP_ADMIN_LOGIN", "u")
    monkeypatch.setenv("DSP_ADMIN_PASSWORD", "p")

    def handler(request):
        import json as _j
        body = _j.loads(request.content)
        if body["method"] == "user.auth":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"access_token": "T"}})
        assert request.headers["Authorization"] == "Bearer T"
        assert body["params"]["filter"]["main_group"] == ["placement"]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": [
            {"placement": "35319", "shows": "8474", "clicks": 0}]})
    got = admin.block_shows(__import__("datetime").date(2026, 10, 1), ["35319", "37405"],
                            transport=httpx.MockTransport(handler))
    assert got == {"35319": (8474, 0), "37405": (0, 0)}
