# -*- coding: utf-8 -*-
"""Токен, выданный до «выключил → включил» учётку, больше не работает.

Внешний аудит 06.10.2026 (подтверждено замером): отзыв токена держался на `is_active` и отпечатке
пароля `pwv`. Деактивация давала 401, но возврат `is_active = 1` отпечаток не менял, и тот же токен
снова проходил. А учётку удалить нельзя (на неё ссылается журнал действий), поэтому «выключил, потом
включил» — штатный путь, и им оживали токены, выданные до выключения.

Теперь в отпечаток входит счётчик `users.token_epoch`, он растёт при каждой смене активности.
Для счётчика 0 отпечаток считается ТАК ЖЕ, как раньше: выкладка не разлогинивает никого.

Тест пишет только свои строки (почты `zz-epoch-…@example.test`) и убирает их; журнал действий подменён.
"""
import hashlib
import hmac
import types
import uuid

import pytest
from fastapi import HTTPException

from app.models import AuditLog, User
from app.routers import auth, users


@pytest.fixture(autouse=True)
def _no_journal(monkeypatch):
    monkeypatch.setattr(users, "log_action", lambda *a, **k: None)


@pytest.fixture
def person(db):
    email = f"zz-epoch-{uuid.uuid4().hex[:10]}@example.test"
    out = users.create_user(users.UserCreate(name="Т", email=email, password="надёжный-пароль-1"),
                            db=db, current_user=types.SimpleNamespace(id=0, name="админ"))
    uid = out["id"]
    yield uid
    db.query(AuditLog).filter(AuditLog.user_id == uid).update({"user_id": None})
    db.query(User).filter(User.id == uid).delete()
    db.commit()


def _token(db, uid):
    db.expire_all()
    return auth.create_access_token(auth.token_claims(db.get(User, uid)))


def _valid(db, token):
    try:
        auth.get_current_user_any(token, db)
        return True
    except HTTPException:
        return False


def _toggle(db, uid, active):
    users.update_user(uid, users.UserUpdate(is_active=active), db=db,
                      current_user=types.SimpleNamespace(id=0, name="админ"))


def test_a_token_from_before_the_switch_off_and_on_stays_dead(db, person):
    old = _token(db, person)
    assert _valid(db, old)
    _toggle(db, person, False)
    assert not _valid(db, old), "выключенная учётка принимает токен"
    _toggle(db, person, True)
    assert not _valid(db, old), "токен, выданный ДО выключения, ожил после включения"
    assert _valid(db, _token(db, person)), "новый токен после включения должен работать"


def test_the_counter_grows_on_every_activity_change_and_only_then(db, person):
    assert db.get(User, person).token_epoch == 0
    users.update_user(person, users.UserUpdate(name="Другое имя"), db=db,
                      current_user=types.SimpleNamespace(id=0, name="админ"))
    db.expire_all()
    assert db.get(User, person).token_epoch == 0, "правка имени не должна отзывать токены"
    _toggle(db, person, False)
    db.expire_all()
    assert db.get(User, person).token_epoch == 1
    _toggle(db, person, True)
    db.expire_all()
    assert db.get(User, person).token_epoch == 2
    _toggle(db, person, True)           # без изменения — счётчик на месте
    db.expire_all()
    assert db.get(User, person).token_epoch == 2


def test_a_zero_counter_keeps_the_old_fingerprint_so_nobody_is_logged_out(db, person):
    """Выкладка не должна разлогинить людей: при счётчике 0 отпечаток тот же, что и раньше."""
    u = db.get(User, person)
    old_formula = hmac.new(auth.SECRET_KEY.encode(), (u.hashed_password or "").encode(),
                           hashlib.sha256).hexdigest()[:16]
    assert auth.password_fingerprint(u) == old_formula


def test_a_changed_counter_changes_the_fingerprint(db, person):
    u = db.get(User, person)
    before = auth.password_fingerprint(u)
    u.token_epoch = 1
    assert auth.password_fingerprint(u) != before


def test_a_password_change_still_kills_old_tokens(db, person):
    old = _token(db, person)
    users.update_user(person, users.UserUpdate(password="совсем-новый-пароль-2"), db=db,
                      current_user=types.SimpleNamespace(id=0, name="админ"))
    assert not _valid(db, old)
