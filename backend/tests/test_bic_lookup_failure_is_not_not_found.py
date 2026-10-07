# -*- coding: utf-8 -*-
"""Поиск банка по БИК: «справочники недоступны» не равно «БИК не найден».

Оба источника (bik-info.ru и ЦБ) глотали любую ошибку, и при отказе обоих человек видел
«БИК не найден» — то есть шёл перепроверять верный БИК (аудит 06.10.2026). Теперь отказ
источников — 503 с понятным текстом, а 404 остаётся для случая, когда источник ответил, но
такого банка нет.
"""
import types

import httpx
import pytest
from fastapi import HTTPException

from app.routers import counterparties as C


class _Resp:
    def __init__(self, status=200, js=None, content=b"<root/>"):
        self.status_code, self._js, self.content = status, js or {}, content

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)


def _call(bik="044525593"):
    return C.lookup_bic(bik, current_user=types.SimpleNamespace())


def test_both_sources_down_is_503_not_404(monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("нет сети")
    monkeypatch.setattr(httpx, "get", down)
    with pytest.raises(HTTPException) as e:
        _call()
    assert e.value.status_code == 503 and "недоступ" in e.value.detail


def test_sources_answered_but_no_such_bank_is_404(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200, {}, b"<root/>"))
    with pytest.raises(HTTPException) as e:
        _call()
    assert e.value.status_code == 404


def test_first_source_down_second_answers_is_not_an_error(monkeypatch):
    def get(url, **k):
        if "bik-info" in url:
            raise httpx.ConnectError("нет сети")
        return _Resp(200, content="<root><Record><ShortName>Банк</ShortName></Record></root>".encode())
    monkeypatch.setattr(httpx, "get", get)
    assert _call()["bank_name"] == "Банк"


def test_first_source_answers_is_used(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200, {"namep": "Банк 1", "city": "москва", "ks": "301"}))
    out = _call()
    assert out == {"bik": "044525593", "bank_name": "Банк 1", "bank_city": "Москва", "ks": "301"}
