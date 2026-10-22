# -*- coding: utf-8 -*-
"""Отзыв входов кабинета (внешний аудит 2.6.76, п. 1.6; сделано 22.10.2026).

«Выйти» стирал токен только в браузере, а «отключил → включил» учётку оживлял токены, выданные до отключения: в токене был
лишь отпечаток пароля. Теперь в отпечатке ещё счётчик `token_epoch` — растёт при «Выйти» (`pub.logout`) и при отключении/
включении (ядро). Счётчик 0 даёт прежний отпечаток: уже выданные входы не слетают. Чтение базы подменяется."""
import os
import sys

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth as cab_auth          # noqa: E402


def _creds(token):
    return HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)


class _Row:
    id, email, name = 1, 'a@b.test', 'Тест'
    is_active, can_approve, consent_accepted_at = True, True, None
    hashed_password = '$2b$12$same'
    token_epoch = 0


@pytest.fixture
def db(monkeypatch):
    calls = []

    class _Db:
        def execute(self, sql, params=None):
            calls.append(str(sql))
            return type('R', (), {'first': staticmethod(lambda: _Row()),
                                  'scalar': staticmethod(lambda: _Row.token_epoch + 1)})()

        def commit(self):
            calls.append('commit')

        def close(self):
            pass
    monkeypatch.setattr(cab_auth, 'plain_session', lambda: _Db())
    _Row.token_epoch = 0
    return calls


def test_zero_epoch_keeps_the_old_fingerprint():
    assert cab_auth.password_fingerprint('$2b$12$x') == cab_auth.password_fingerprint('$2b$12$x', 0)


def test_token_dies_when_epoch_grows(db):
    token = cab_auth.make_token(1, 'a@b.test')
    assert cab_auth.current_account_any(_creds(token)).id == 1
    _Row.token_epoch = 1
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account_any(_creds(token))
    assert e.value.status_code == 401


def test_new_token_after_epoch_grows_is_accepted(db):
    _Row.token_epoch = 3
    token = cab_auth.make_token(1, 'a@b.test')
    assert cab_auth.current_account_any(_creds(token)).id == 1


def test_logout_calls_the_revoke_function(db):
    cab_auth.revoke_sessions(1)
    assert any('pub.logout' in c for c in db) and 'commit' in db
