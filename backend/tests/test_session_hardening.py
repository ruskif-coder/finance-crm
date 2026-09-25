# -*- coding: utf-8 -*-
"""Сессии ядра: смена пароля отзывает токены, проверка пароля ограничена, согласие держит
сервер (аудит 23.09.2026, этап 9: 9.2, 9.3, 9.7).

9.2 — токен жил 8 часов и после смены пароля: сброс пароля не выкидывал украденную
сессию. Теперь в токене отпечаток хеша пароля; сменился пароль — токен недействителен.
9.3 — `/auth/verify-password` не ограничивал попытки: пароль учётки подбирался в обход
блокировки входа. Теперь общий со входом счётчик.
9.7 — согласие на обработку ПДн держал только экран входа. Теперь сервер: без согласия
открыты «кто я» и само принятие (решение владельца 24.09.2026 — как в кабинете).
"""
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import auth


class _Db:
    def __init__(self, user):
        self.user = user

    def query(self, model):
        u = self.user
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: u))


def _user(pw_hash='$2b$12$old', consent=True):
    return SimpleNamespace(email='x@example.invalid', is_active=1, hashed_password=pw_hash,
                           consent_accepted_at=object() if consent else None,
                           role=SimpleNamespace(key='manager'))


def test_a_token_dies_with_the_password():
    u = _user()
    token = auth.create_access_token(auth.token_claims(u))
    assert auth.get_current_user(token, _Db(u)) is u
    u.hashed_password = '$2b$12$new'
    with pytest.raises(HTTPException) as e:
        auth.get_current_user(token, _Db(u))
    assert e.value.status_code == 401


def test_a_token_without_the_fingerprint_is_refused():
    u = _user()
    token = auth.create_access_token({'sub': u.email, 'role': 'manager'})
    with pytest.raises(HTTPException) as e:
        auth.get_current_user(token, _Db(u))
    assert e.value.status_code == 401


def test_login_issues_the_fingerprinted_token():
    assert 'token_claims(user)' in inspect.getsource(auth.login)


def test_verify_password_shares_the_login_lockout():
    src = inspect.getsource(auth.verify_current_password)
    assert '_check_login_lockout(' in src and '_register_failed_login(' in src


def test_without_consent_data_is_refused_but_me_and_accept_work():
    u = _user(consent=False)
    token = auth.create_access_token(auth.token_claims(u))
    with pytest.raises(HTTPException) as e:
        auth.get_current_user(token, _Db(u))
    assert e.value.status_code == 403 and e.value.detail == auth.CONSENT_REQUIRED
    assert auth.get_current_user_any(token, _Db(u)) is u
    for fn in (auth.get_me, auth.accept_consent):
        deps = [p.default.dependency for p in inspect.signature(fn).parameters.values()
                if hasattr(p.default, 'dependency')]
        assert auth.get_current_user_any in deps, f"{fn.__name__} закрыт без согласия"


def test_a_wrong_confirmation_password_does_not_end_the_session():
    """Неверный пароль в окне подтверждения — 403, а не 401: 401 фронт читает как
    «сессия истекла» и выкидывает на вход после одной опечатки (ревью 24.09.2026)."""
    src = inspect.getsource(auth.verify_current_password)
    assert 'status_code=401' not in src and 'status_code=403' in src
