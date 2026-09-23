# -*- coding: utf-8 -*-
"""Прибор на заслон из conftest: тест не выходит во внешние системы (ревью 23.09.2026).

Без этой проверки заслон мог бы молча перестать работать — например, если транспорт
Битрикса перейдёт на свой `httpx.Client` — и следующий сломанный тест снова записал бы
бриф в настоящую сделку.
"""
import smtplib

import httpx
import pytest

from app.notify import telegram
from app.sales.bitrix import transport
from tests.conftest import NetworkInTest


def test_bitrix_write_is_stopped(monkeypatch):
    monkeypatch.setenv("VIBECODE_API_KEY", "прибор")
    with pytest.raises(NetworkInTest):
        transport.vibecode_patch("/deals/1", {"x": 1})


def test_bitrix_read_is_stopped(monkeypatch):
    monkeypatch.setenv("VIBECODE_API_KEY", "прибор")
    with pytest.raises(NetworkInTest):
        transport.vibecode_get("/deals/1", {})


def test_telegram_host_is_stopped():
    with pytest.raises(NetworkInTest):
        httpx.post(telegram.API.format(token="t", method="sendMessage"), json={})


def test_own_client_is_stopped_too():
    with httpx.Client() as c, pytest.raises(NetworkInTest):
        c.get("https://example.org/")


def test_smtp_is_stopped():
    with pytest.raises(NetworkInTest):
        smtplib.SMTP("smtp.example.org", 25)


def test_mock_transport_still_works():
    t = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    with httpx.Client(transport=t) as c:
        assert c.get("https://api.example.org/x").json() == {"ok": True}
