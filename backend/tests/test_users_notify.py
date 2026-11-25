# -*- coding: utf-8 -*-
"""Уведомления экрана «Пользователи» (макет 16.11.2026, владелец: «блоком уведомлений так же»).

Действие администратора → событие: создан (администраторам; самому — письмо о входе, БЕЗ пароля), сброшен пароль
(самому), сменена роль (самому и администраторам), назначена или снята роль «Администратор» (всем администраторам),
деактивирован или возвращён (администраторам и мастеру его группы), удалён (администраторам). События уходят ПОСЛЕ
коммита: не сохранилось — не о чем сообщать. Тест пишет только свои строки (`zz-unotify-…@example.test`)."""
import types
import uuid

import pytest

from app.models import AuditLog, Role, User
from app.notify import recipients as rcp
from app.routers import users

PW = "надёжный-пароль-1"


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(users, "log_action", lambda *a, **k: None)
    from app.notify import bus
    monkeypatch.setattr(bus, "emit", lambda db, key, **kw: out.append((key, kw)) or [])
    return out


@pytest.fixture
def made(db):
    yield
    db.rollback()
    # Профиль продавца отвязываем ПЕРЕД удалением учётки: с 25.11.2026 создание сейлза заводит
    # строку в `sales_reps`, и `delete users` без этого упирается во внешний ключ.
    from app.sales.models import SalesRep
    for u in db.query(User).filter(User.email.like("zz-unotify-%")).all():
        db.query(SalesRep).filter(SalesRep.user_id == u.id).delete()
        db.query(AuditLog).filter(AuditLog.user_id == u.id).update({"user_id": None})
        db.delete(u)
    db.commit()


def _admin():
    return types.SimpleNamespace(id=0, name="админ теста")


def _email():
    return f"zz-unotify-{uuid.uuid4().hex[:10]}@example.test"


def _batch(db, *changes):
    return users.save_users_batch(users.UsersBatch(changes=[users.UserPatch(**c) for c in changes]), db=db,
                                  current_user=_admin())


def _new(db, role="viewer"):
    out = _batch(db, {"new": True, "name": "Тест Уведомлений", "email": _email(), "role": role, "password": PW})
    return out["created"][0]


def _keys(sent):
    return [k for k, _ in sent]


def test_created_user_notifies_admins_and_welcomes_without_password(db, made, sent):
    uid = _new(db)
    assert _keys(sent) == ["user_created", "user_welcome"]
    welcome = sent[1][1]
    assert welcome["user_ids"] == [uid] and PW not in (welcome["body"] or "") and PW not in sent[0][1]["body"]


def test_password_reset_tells_the_user_only_that_it_was_reset(db, made, sent):
    uid = _new(db); sent.clear()
    _batch(db, {"id": uid, "password": "новый-пароль-22"})
    assert _keys(sent) == ["user_password_reset"]
    assert sent[0][1]["ctx"]["user"].id == uid and "новый-пароль-22" not in sent[0][1]["body"]


def test_role_change_and_admin_grant(db, made, sent):
    uid = _new(db); sent.clear()
    other = db.query(Role).filter(Role.key != "viewer", Role.key != "admin").first()
    _batch(db, {"id": uid, "role": other.key})
    assert _keys(sent) == ["user_role_changed"]
    sent.clear()
    _batch(db, {"id": uid, "role": "admin"})
    assert _keys(sent) == ["user_role_changed", "user_admin_role"]
    sent.clear()
    _batch(db, {"id": uid, "role": "viewer"})
    assert _keys(sent) == ["user_role_changed", "user_admin_role"]          # снятие — тоже всем администраторам


def test_deactivation_return_and_deletion(db, made, sent):
    uid = _new(db); sent.clear()
    _batch(db, {"id": uid, "is_active": False})
    _batch(db, {"id": uid, "is_active": True})
    _batch(db, {"id": uid, "is_active": False})
    _batch(db, {"id": uid, "delete": True})
    assert _keys(sent) == ["user_activity_changed"] * 3 + ["user_deleted"]
    assert "деактивирован" in sent[0][1]["title"] and "возвращ" in sent[1][1]["title"]


def test_nothing_is_sent_when_the_batch_fails(db, made, sent):
    uid = _new(db); sent.clear()
    with pytest.raises(Exception):
        _batch(db, {"id": uid, "is_active": False}, {"new": True, "name": "", "email": "x@example.test", "password": PW})
    assert sent == []


def test_resolvers_subject_user_and_master_of_his_group(db, made, sent):
    uid = _new(db)
    u = db.get(User, uid)
    assert rcp.RESOLVERS["subject_user"](db, {"user": u}) == [uid]
    seller = db.query(Role).filter(Role.staff_group == "seller").first()
    if seller is None:
        pytest.skip("на стенде нет группы продавцов")
    u.role_id = seller.id
    db.commit()
    masters = rcp.RESOLVERS["group_master_of_user"](db, {"user": u})
    ids = {r.id for r in db.query(Role).filter(Role.staff_group == "seller", Role.is_master.is_(True))}
    assert all(db.get(User, m).role_id in ids for m in masters)
    assert rcp.RESOLVER_CTX["subject_user"] == "user" and rcp.RESOLVER_CTX["group_master_of_user"] == "user"
