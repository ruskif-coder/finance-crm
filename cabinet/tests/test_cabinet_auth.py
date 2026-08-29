# -*- coding: utf-8 -*-
"""Вход и сессия внешнего контура. Первые приборы на стороне САМОГО кабинета.

До 30.08.2026 тестов здесь не было вовсе: контракт с базой проверялся из ядра
(`backend/tests/test_cabinet_contract.py`), шлюз — тоже из ядра, а всё, что живёт только
в этом процессе — разбор токена, живость учётки, область видимости запроса — не
проверялось ничем.

Прогон:
    docker exec cabinet_backend python -m pytest tests -q

Приборы идут по живой базе стенда и НИЧЕГО в ней не меняют: читают учётку, подписывают
свои токены, проверяют отказы. Выключить учётку отсюда нельзя в принципе — роль кабинета
не может стать ролью ядра, и на этом стоит весь контур; поэтому в тесте живости
подменяется чтение, а сам запрет вынесен в отдельный прибор.
"""
import os
import sys

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth as cab_auth          # noqa: E402
from app.db import plain_session          # noqa: E402


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)


@pytest.fixture
def account():
    db = plain_session()
    try:
        row = db.execute(text(
            "SELECT id, email, name, is_active, can_approve FROM pub.account_v1 "
            "ORDER BY id LIMIT 1")).first()
    finally:
        db.close()
    if row is None:
        pytest.skip('на стенде нет ни одной учётки кабинета')
    return row


# ── токен ────────────────────────────────────────────────────────────────────

def test_own_token_is_accepted(account):
    """Иначе все отказы ниже зелены и при вечно закрытом входе."""
    got = cab_auth.current_account(_creds(cab_auth.make_token(account.id, account.email)))
    assert got.id == account.id


def test_token_signed_with_another_key_is_rejected(account):
    """Ключи двух контуров разные — и это не гигиена.

    С общим ключом токен, выписанный кабинетом ВНЕШНЕМУ лицу, был бы валиден и для
    финмодуля. Здесь проверяется, что подмена не собирается даже случайно.
    """
    import jwt
    from datetime import datetime, timedelta, timezone
    alien = jwt.encode({'sub': str(account.id), 'email': account.email,
                        'realm': 'cabinet',
                        'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                       'ключ-финмодуля-а-не-кабинета', algorithm='HS256')
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(_creds(alien))
    assert e.value.status_code == 401


def test_token_from_another_realm_is_rejected(account):
    """Даже правильно подписанный токен без `realm=cabinet` не пускает.

    Realm — вторая защёлка на случай, если ключи однажды сведут в один: подпись сойдётся,
    а назначение токена нет.
    """
    import jwt
    from datetime import datetime, timedelta, timezone
    core_like = jwt.encode({'sub': str(account.id), 'email': account.email,
                            'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                           cab_auth.SECRET_KEY, algorithm=cab_auth.ALGORITHM)
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(_creds(core_like))
    assert e.value.status_code == 401


def test_expired_token_is_rejected(account):
    import jwt
    from datetime import datetime, timedelta, timezone
    old = jwt.encode({'sub': str(account.id), 'email': account.email, 'realm': 'cabinet',
                      'exp': datetime.now(timezone.utc) - timedelta(minutes=1)},
                     cab_auth.SECRET_KEY, algorithm=cab_auth.ALGORITHM)
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(_creds(old))
    assert e.value.status_code == 401


def test_no_credentials_is_rejected():
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(None)
    assert e.value.status_code == 401


def test_token_for_a_missing_account_is_rejected(account):
    """Учётку могли удалить — токен обязан перестать работать сразу."""
    ghost = cab_auth.make_token(10 ** 9, 'ghost@nowhere.test')
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(_creds(ghost))
    assert e.value.status_code in (401, 403)


# ── живость учётки ───────────────────────────────────────────────────────────

def test_deactivated_account_loses_access_immediately(account, monkeypatch):
    """Отключение действует СРАЗУ, а не через 12 часов.

    Токен живёт полсуток; если живость проверять только при входе, «доступ закрыт»
    означало бы «закрыт послезавтра».

    Учётку здесь НЕ выключаем в базе, и не по лени: первая версия теста делала
    `SET LOCAL ROLE finance_user` — и упала с `permission denied to set role`. Это не
    помеха, а сама изоляция: роль кабинета не может стать ролью ядра даже в собственном
    тесте. Поэтому подменяется ЧТЕНИЕ — проверяется ветка, а не способность обойти
    границу.
    """
    token = cab_auth.make_token(account.id, account.email)
    assert cab_auth.current_account(_creds(token)).id == account.id

    class _Row:
        id, email, name = account.id, account.email, account.name
        is_active, can_approve = False, True

    class _Db:
        def execute(self, *a, **k):
            return type('R', (), {'first': staticmethod(lambda: _Row())})()

        def close(self):
            pass

    monkeypatch.setattr(cab_auth, 'plain_session', lambda: _Db())
    with pytest.raises(HTTPException) as e:
        cab_auth.current_account(_creds(token))
    assert e.value.status_code == 403


def test_cabinet_cannot_become_the_core_role():
    """Роль кабинета не может стать ролью ядра — на этом стоит весь внешний контур.

    Отдельный прибор, потому что предыдущий тест наткнулся на это случайно. Случайная
    защита однажды снимается вместе с тем, что её ставило.
    """
    from sqlalchemy.exc import ProgrammingError
    db = plain_session()
    try:
        with pytest.raises((ProgrammingError, Exception)) as e:
            db.execute(text('SET LOCAL ROLE finance_user'))
            db.commit()
        assert 'permission denied' in str(e.value).lower()
    finally:
        db.rollback()
        db.close()


# ── область видимости ────────────────────────────────────────────────────────

def test_scope_is_local_to_the_transaction():
    """`set_config(..., is_local => true)` обнуляется при возврате соединения в пул.

    Обычный `SET` пережил бы возврат и достался следующему паблишеру — то есть один
    показал бы задания другого. Проверяется в ДВУХ последовательных сессиях: если бы
    область видимости текла, вторая унаследовала бы первую.
    """
    from app.db import scoped_session
    with scoped_session([1, 2, 3]) as db:
        assert db.execute(text("SELECT current_setting('app.publisher_ids', true)")
                          ).scalar() == '1,2,3'
    db2 = plain_session()
    try:
        left = db2.execute(text("SELECT current_setting('app.publisher_ids', true)")).scalar()
    finally:
        db2.close()
    assert not left, f'область видимости пережила транзакцию: {left!r}'


def test_empty_scope_shows_nothing():
    """Пустой список площадок — пустой доступ, а не полный.

    Это ровно тот случай, где ошибка в одну сторону стоит утечки: `allowed_publisher_ids`
    на пустой строке обязана вернуть пустой массив, а не все идентификаторы.
    """
    from app.db import scoped_session
    with scoped_session([]) as db:
        n = db.execute(text("SELECT count(*) FROM pub.task_v1")).scalar()
    assert n == 0
