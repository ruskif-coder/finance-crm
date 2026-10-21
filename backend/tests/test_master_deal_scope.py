# -*- coding: utf-8 -*-
"""Область видимости у мастер-сделки (проверка прав 16.10.2026).

Пакет находится по коду, мимо `SalesDeal`, и прибор `test_deal_scope` его не видит. Роль с
областью «свои» не должна открывать и править пакет, где нет ни одной её сделки."""
import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.master_deal import scope as SC
from app.routers import master_deals as R


class _M:
    id = 1
    code = "M-TEST"


def test_own_scope_without_own_deals_is_denied(monkeypatch):
    monkeypatch.setattr(SC, "package_owners", lambda db, m: [(1, 2), (3, None)])
    assert not SC.in_scope(None, _M(), {999})


def test_own_scope_with_one_own_deal_passes(monkeypatch):
    monkeypatch.setattr(SC, "package_owners", lambda db, m: [(1, 2), (3, None)])
    assert SC.in_scope(None, _M(), {2})


def test_scope_all_passes_without_reading_package(monkeypatch):
    monkeypatch.setattr(SC, "package_owners", lambda db, m: pytest.fail("при «все» пакет не читаем"))
    assert SC.in_scope(None, _M(), None)


def test_router_refuses_out_of_scope_with_403(monkeypatch):
    class _Q:
        def filter(self, *a): return self
        def first(self): return _M()
    class _DB:
        def query(self, *a): return _Q()
    monkeypatch.setattr(SC, "own_reps", lambda db, user: {999})
    monkeypatch.setattr(SC, "package_owners", lambda db, m: [(1, 2)])
    with pytest.raises(HTTPException) as e:
        R._master(_DB(), "M-TEST", object())
    assert e.value.status_code == 403


def test_every_route_resolves_master_with_user():
    import inspect
    src = inspect.getsource(R)
    assert "_master(db, code)" not in src, "ручка берёт пакет без проверки области"
