# -*- coding: utf-8 -*-
"""Пакетное сохранение пользователей (экран «Пользователи» по макету 16.11.2026): одно «Сохранить N» на всю страницу.

Правки приходят одним запросом и применяются одной транзакцией: если хоть одна не проходит (свою роль менять нельзя,
занятый email, удалить активного…), не применяется НИЧЕГО, а ответ называет строку. Правила — те же, что у ручек
«по одному» (`create_user`/`update_user`/`delete_user`): пакет зовёт те же функции, своей копии проверок у него нет.

Тест пишет только свои строки (почты `zz-batch-…@example.test`) и убирает их; журнал действий подменён.
"""
import types
import uuid

import pytest
from fastapi import HTTPException

from app.models import AuditLog, LoginAttempt, User
from app.routers import auth, users

PW = "надёжный-пароль-1"


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    calls = []
    monkeypatch.setattr(users, "log_action", lambda db_, user, action, *a, **k: calls.append((action, k.get("details", ""))))
    return calls


@pytest.fixture
def made(db):
    box = []
    yield box
    db.rollback()
    ids = box + [u.id for u in db.query(User).filter(User.email.like("zz-batch-%")).all()]
    for uid in set(ids):
        db.query(AuditLog).filter(AuditLog.user_id == uid).update({"user_id": None})
        db.query(User).filter(User.id == uid).delete()
    db.query(LoginAttempt).filter(LoginAttempt.email.like("zz-batch-%")).delete(synchronize_session=False)
    db.commit()


def _admin(uid=0):
    return types.SimpleNamespace(id=uid, name="админ теста")


def _email():
    return f"zz-batch-{uuid.uuid4().hex[:10]}@example.test"


def _user(db, made, role="viewer"):
    out = users.create_user(users.UserCreate(name="Тест", email=_email(), password=PW, role=role), db=db, current_user=_admin())
    made.append(out["id"])
    return out["id"]


def _batch(db, *changes, me=0):
    return users.save_users_batch(users.UsersBatch(changes=[users.UserPatch(**c) for c in changes]), db=db,
                                  current_user=_admin(me))


def test_create_update_and_delete_go_in_one_request(db, made, audit):
    a, gone = _user(db, made), _user(db, made)
    users.update_user(gone, users.UserUpdate(is_active=False), db=db, current_user=_admin())
    new_email = _email()
    audit.clear()
    out = _batch(db, {"new": True, "name": "Новый Человек", "email": new_email, "role": "viewer", "password": PW},
                 {"id": a, "name": "Переименован", "is_active": False},
                 {"id": gone, "delete": True})
    db.expire_all()
    fresh = db.query(User).filter(User.email == new_email).one()
    assert out["created"] == [fresh.id] and fresh.name == "Новый Человек"
    assert auth.verify_password(PW, fresh.hashed_password)
    assert db.get(User, a).name == "Переименован" and not db.get(User, a).is_active
    assert db.get(User, gone) is None
    assert [c[0] for c in audit] == ["create_user", "update_user", "delete_user"]


def test_one_bad_change_rolls_back_everything_and_names_the_row(db, made, audit):
    a = _user(db, made)
    busy = db.get(User, _user(db, made)).email
    with pytest.raises(HTTPException) as e:
        _batch(db, {"id": a, "name": "Не должно сохраниться"},
               {"new": True, "name": "Двойник", "email": busy, "role": "viewer", "password": PW})
    assert e.value.status_code == 400
    assert "Двойник" in e.value.detail and "Email уже зарегистрирован" in e.value.detail
    db.expire_all()
    assert db.get(User, a).name == "Тест"
    assert [c[0] for c in audit] == ["create_user", "create_user"]     # только от фикстуры: пакет не записал ничего


@pytest.mark.parametrize("change, word", [
    ({"role": "admin"}, "собственную роль"),
    ({"is_active": False}, "самого себя"),
    ({"delete": True}, "самого себя"),
])
def test_own_role_status_and_deletion_are_refused(db, made, change, word):
    me = _user(db, made)
    with pytest.raises(HTTPException) as e:
        _batch(db, {"id": me, **change}, me=me)
    assert word in e.value.detail


def test_active_user_is_not_deleted(db, made):
    a = _user(db, made)
    with pytest.raises(HTTPException) as e:
        _batch(db, {"id": a, "delete": True})
    assert "деактивируйте" in e.value.detail
    assert db.get(User, a) is not None


@pytest.mark.parametrize("change, word", [
    ({"name": "  ", "email": "ok@example.test"}, "имя"),
    ({"name": "Имя", "email": "без-собаки"}, "email"),
    ({"name": "Имя", "email": "ok@example.test", "password": "коротко"}, "8 символов"),
])
def test_new_user_without_name_valid_email_or_long_password_is_refused(db, made, change, word):
    with pytest.raises(HTTPException) as e:
        _batch(db, {"new": True, "role": "viewer", "password": PW, **change})
    assert word in e.value.detail.lower()


def test_new_user_can_be_created_deactivated_and_with_a_profile(db, made):
    from app.notify.models import NotificationProfile
    prof = db.query(NotificationProfile).order_by(NotificationProfile.id).first()
    if prof is None:
        pytest.skip("на стенде нет профилей уведомлений")
    email = _email()
    _batch(db, {"new": True, "name": "Выключенный", "email": email, "role": "viewer", "password": PW,
                "is_active": False, "notification_profile_id": prof.id})
    db.expire_all()
    u = db.query(User).filter(User.email == email).one()
    assert not u.is_active and u.notification_profile_id == prof.id


def test_unknown_user_is_404_and_empty_batch_is_refused(db, made):
    with pytest.raises(HTTPException) as e:
        _batch(db, {"id": 10 ** 9, "name": "Нет такого"})
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        _batch(db)
    assert e.value.status_code == 400


def test_profiles_list_says_which_profile_a_role_starts_with(db):
    out = users.notification_profiles(db=db, current_user=_admin())
    assert isinstance(out["by_role"], dict) and isinstance(out["profiles"], list)
    if out["profiles"]:
        assert {"id", "label", "is_default"} <= set(out["profiles"][0])
