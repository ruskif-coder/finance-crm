# -*- coding: utf-8 -*-
"""Согласие на обработку персональных данных (владелец, 24.09.2026).

Как у сотрудников: при первом входе человек принимает политику и согласие. Держит это
СЕРВЕР: ручки с данными отказывают учётке без согласия, иначе экран согласия обходится
прямым вызовом API. Без согласия доступны только «кто я» (экрану надо знать, что
показывать) и само принятие.

Роль кабинета не может менять учётку — поэтому, как и в `test_cabinet_auth`, здесь
подменяется ЧТЕНИЕ, а запись проверяется по тому, КАКУЮ функцию ядра зовёт ручка.
"""
import inspect
import os
import sys
from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth as cab_auth          # noqa: E402
from app import main as cab_main          # noqa: E402


def _creds(token):
    return HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)


def _fake_db(consent_at):
    class _Row:
        id, email, name = 7, 'x@example.invalid', 'Тест'
        is_active, can_approve = True, True
        consent_accepted_at = consent_at

    class _Db:
        sql = []

        def execute(self, stmt, *a, **k):
            _Db.sql.append(str(stmt))
            return type('R', (), {'first': staticmethod(lambda: _Row()),
                                  'scalar': staticmethod(lambda: datetime(2026, 9, 24))})()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass
    return _Db


def test_data_is_refused_without_consent(monkeypatch):
    monkeypatch.setattr(cab_auth, 'plain_session', lambda: _fake_db(None)())
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(_creds(cab_auth.make_token(7, 'x@example.invalid')))
    assert e.value.status_code == 403
    assert e.value.detail == cab_auth.CONSENT_REQUIRED


def test_with_consent_data_is_given(monkeypatch):
    monkeypatch.setattr(cab_auth, 'plain_session', lambda: _fake_db(datetime(2026, 9, 1))())
    got = cab_auth.current_account(_creds(cab_auth.make_token(7, 'x@example.invalid')))
    assert got.id == 7


def test_who_am_i_works_before_consent_and_says_so(monkeypatch):
    monkeypatch.setattr(cab_auth, 'plain_session', lambda: _fake_db(None)())
    acc = cab_auth.current_account_any(_creds(cab_auth.make_token(7, 'x@example.invalid')))
    monkeypatch.setattr(cab_main, 'account_publishers', lambda i: [])
    assert cab_main.me(acc)['consent_required'] is True


def test_accepting_goes_through_the_core_function(monkeypatch):
    db = _fake_db(None)
    db.sql = []
    monkeypatch.setattr(cab_main, 'plain_session', lambda: db())
    acc = type('A', (), {'id': 7})()
    out = cab_main.accept_consent(acc)
    assert any('pub.accept_consent' in q for q in db.sql)
    assert out['consent_required'] is False


def test_login_tells_the_screen_about_consent():
    src = inspect.getsource(cab_main.login)
    assert '"consent_required"' in src


def test_only_two_doors_open_without_consent():
    """Ратчет: новая ручка по умолчанию закрыта без согласия. Открытых без него — ровно
    две: «кто я» и само принятие."""
    open_ = set()
    for route in cab_main.app.routes:
        deps = [d.call for d in getattr(getattr(route, 'dependant', None), 'dependencies', [])]
        if cab_auth.current_account_any in deps:
            open_.add(route.path)
    assert open_ == {'/api/me', '/api/consent'}, open_
