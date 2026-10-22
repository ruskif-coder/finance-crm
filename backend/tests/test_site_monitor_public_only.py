# -*- coding: utf-8 -*-
"""Монитор сайтов ходит только на публичные адреса (аудит 2.6.76, п. 1.13; владелец 22.10.2026: «1.13 делай»).
Домен площадки вписывают люди: внутренний адрес превращал монитор в запросчик к нашей же сети — со следованием редиректам и
чтением ответа целиком. Теперь: только http(s) на публичный IP, редиректы — вручную с той же проверкой каждого шага,
тело ответа не читается. Сеть подменяется."""
import socket

import httpx
import pytest

from app.traffic import site_monitor as SM


def _resolve(mapping):
    def fake(host, *a, **k):
        ip = mapping.get(host)
        if ip is None:
            raise socket.gaierror("нет такого")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]
    return fake


@pytest.fixture(autouse=True)
def dns(monkeypatch):
    monkeypatch.setattr(SM.socket, "getaddrinfo", _resolve({
        "example.com": "93.184.216.34", "evil.test": "10.0.0.5", "localhost": "127.0.0.1", "meta.test": "169.254.169.254"}))


@pytest.mark.parametrize("url,ok", [
    ("https://example.com/", True), ("http://example.com", True),
    ("http://127.0.0.1/", False), ("http://10.1.2.3/x", False), ("http://localhost:8000/", False),
    ("http://evil.test/", False), ("http://169.254.169.254/latest/meta-data", False), ("http://meta.test/", False),
    ("ftp://example.com/", False), ("http://[::1]/", False), ("http://nowhere.test/", False)])
def test_only_public_http_targets(url, ok):
    assert SM.public_target(url) is ok


def test_redirect_into_internal_network_is_stopped(monkeypatch):
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.5/admin"})
        raise AssertionError("монитор пошёл во внутреннюю сеть")
    monkeypatch.setattr(SM, "_transport", lambda: httpx.MockTransport(handler))
    with pytest.raises(SM.NotPublic):
        SM._http("https://example.com/")


def test_redirects_are_followed_and_body_is_not_needed(monkeypatch):
    def handler(request):
        if request.url.path == "/":
            return httpx.Response(301, headers={"location": "https://example.com/home"})
        return httpx.Response(200, content=b"x" * 10)
    monkeypatch.setattr(SM, "_transport", lambda: httpx.MockTransport(handler))
    got = SM._http("https://example.com/")
    assert got["http_status"] == 200 and got["final_url"] == "https://example.com/home"


def test_check_refuses_internal_address_without_any_request():
    called = []
    out = SM.check("http://10.0.0.9/", "browser", http=lambda u: called.append(u), browser=lambda u: called.append(u))
    assert out["status"] == SM.DOWN and "публичн" in out["message"] and not called
