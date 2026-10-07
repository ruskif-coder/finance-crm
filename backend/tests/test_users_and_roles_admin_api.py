# -*- coding: utf-8 -*-
"""Админские ручки пользователей и ролей: что они разрешают и что запрещают.

ЗАЧЕМ. Покрытие `users.py` и `roles.py` было 34 % и 33 % (замер 07.10.2026), а именно здесь
решается, кто может войти и что видит. Все правила ниже уже были в коде, но ни одно не
держалось тестом: нельзя сменить собственную роль, нельзя деактивировать себя, пароль короче
восьми знаков не принимается, удалить можно только деактивированного, смена пароля снимает
блокировку входа, право `delete` не выдаётся разделу, у которого такого действия нет.

Тест пишет только свои строки (почты `zz-users-…@example.test`, роли `zz …`) и убирает их; лог
действий подменён, чтобы в журнале не оставалось следа.
"""
import types
import uuid

import pytest
from fastapi import HTTPException

from app.models import AuditLog, LoginAttempt, Role, RolePermission, User
from app.permissions import SECTIONS
from app.routers import auth, roles, users

PW = "надёжный-пароль-1"


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    calls = []
    rec = lambda db_, user, action, *a, **k: calls.append((action, k.get("details", "")))  # noqa: E731
    monkeypatch.setattr(users, "log_action", rec)
    monkeypatch.setattr(roles, "log_action", rec)
    return calls


@pytest.fixture
def made(db):
    """Что создал тест — убирается в конце. Порядок важен: сначала пользователи, потом роли."""
    box = {"users": [], "roles": []}
    yield box
    for uid in box["users"]:
        db.query(AuditLog).filter(AuditLog.user_id == uid).update({"user_id": None})
        db.query(User).filter(User.id == uid).delete()
    for rid in box["roles"]:
        db.query(RolePermission).filter(RolePermission.role_id == rid).delete()
        db.query(User).filter(User.role_id == rid).delete()
        db.query(Role).filter(Role.id == rid).delete()
    db.query(LoginAttempt).filter(LoginAttempt.email.like("zz-users-%")).delete(synchronize_session=False)
    db.commit()


def _admin(uid=0):
    return types.SimpleNamespace(id=uid, name="админ теста")


def _email():
    return f"zz-users-{uuid.uuid4().hex[:10]}@example.test"


def _new_user(db, made, role="viewer", email=None, password=PW):
    email = email or _email()
    out = users.create_user(users.UserCreate(name="Тест", email=email, password=password, role=role),
                            db=db, current_user=_admin())
    made["users"].append(out["id"])
    return out["id"], email


def _code(fn, *a, **k):
    try:
        fn(*a, **k)
    except HTTPException as e:
        return e.status_code, e.detail
    return 200, None


# ── пользователи: создание ───────────────────────────────────────────────────

def test_create_user_hashes_the_password_and_sets_the_role(db, made, audit):
    uid, email = _new_user(db, made)
    u = db.get(User, uid)
    assert u.email == email and u.role.key == "viewer"
    assert u.hashed_password != PW and auth.verify_password(PW, u.hashed_password)
    assert audit and audit[-1][0] == "create_user"


@pytest.mark.parametrize("kwargs,detail", [
    ({"password": "коротко"}, "не короче 8"),
    ({"role": "no_such_role"}, "Недопустимая роль"),
])
def test_create_user_refuses_bad_input(db, made, audit, kwargs, detail):
    body = {"name": "Т", "email": _email(), "password": PW, "role": "viewer", **kwargs}
    code, msg = _code(users.create_user, users.UserCreate(**body), db=db, current_user=_admin())
    assert code == 400 and detail in msg
    assert not db.query(User).filter(User.email == body["email"]).first()


def test_create_user_refuses_a_taken_email(db, made, audit):
    _, email = _new_user(db, made)
    code, msg = _code(users.create_user, users.UserCreate(name="Т", email=email, password=PW),
                      db=db, current_user=_admin())
    assert code == 400 and "уже зарегистрирован" in msg


def test_create_user_takes_the_notification_profile_from_the_request(db, made, audit):
    from app.notify.models import NotificationProfile
    prof = db.query(NotificationProfile).order_by(NotificationProfile.id).first()
    out = users.create_user(users.UserCreate(name="Т", email=_email(), password=PW,
                                             notification_profile_id=prof.id),
                            db=db, current_user=_admin())
    made["users"].append(out["id"])
    assert db.get(User, out["id"]).notification_profile_id == prof.id


# ── пользователи: правка ─────────────────────────────────────────────────────

def test_update_unknown_user_is_404(db, audit):
    assert _code(users.update_user, 999999999, users.UserUpdate(name="x"), db=db,
                 current_user=_admin())[0] == 404


def test_update_changes_name_and_logs_it(db, made, audit):
    uid, _ = _new_user(db, made)
    users.update_user(uid, users.UserUpdate(name="Новое имя"), db=db, current_user=_admin())
    assert db.get(User, uid).name == "Новое имя"
    assert audit[-1][0] == "update_user" and "Новое имя" in audit[-1][1]


def test_update_without_changes_writes_nothing_to_the_journal(db, made, audit):
    uid, _ = _new_user(db, made)
    n = len(audit)
    users.update_user(uid, users.UserUpdate(name="Тест"), db=db, current_user=_admin())
    assert len(audit) == n


@pytest.mark.parametrize("bad", ["", "без-собаки"])
def test_update_refuses_an_email_without_at(db, made, audit, bad):
    uid, _ = _new_user(db, made)
    code, msg = _code(users.update_user, uid, users.UserUpdate(email=bad or " "), db=db,
                      current_user=_admin())
    assert code == 400 and "email" in msg.lower()


def test_update_refuses_an_email_that_belongs_to_someone_else(db, made, audit):
    a, _ = _new_user(db, made)
    _, other = _new_user(db, made)
    code, msg = _code(users.update_user, a, users.UserUpdate(email=other), db=db, current_user=_admin())
    assert code == 400 and "занят" in msg


def test_nobody_changes_their_own_role(db, made, audit):
    uid, _ = _new_user(db, made)
    me = types.SimpleNamespace(id=uid, name="я")
    code, msg = _code(users.update_user, uid, users.UserUpdate(role="manager"), db=db, current_user=me)
    assert code == 400 and "собственную роль" in msg
    assert db.get(User, uid).role.key == "viewer"


def test_admin_changes_someone_elses_role_and_unknown_role_is_refused(db, made, audit):
    uid, _ = _new_user(db, made)
    users.update_user(uid, users.UserUpdate(role="manager"), db=db, current_user=_admin())
    assert db.get(User, uid).role.key == "manager"
    assert _code(users.update_user, uid, users.UserUpdate(role="no_such"), db=db,
                 current_user=_admin())[0] == 400


def test_nobody_deactivates_themselves_but_others_toggle(db, made, audit):
    uid, _ = _new_user(db, made)
    me = types.SimpleNamespace(id=uid, name="я")
    code, msg = _code(users.update_user, uid, users.UserUpdate(is_active=False), db=db, current_user=me)
    assert code == 400 and "самого себя" in msg
    users.update_user(uid, users.UserUpdate(is_active=False), db=db, current_user=_admin())
    assert not db.get(User, uid).is_active
    users.update_user(uid, users.UserUpdate(is_active=True), db=db, current_user=_admin())
    assert db.get(User, uid).is_active


def test_short_password_is_refused_and_long_one_is_hashed(db, made, audit):
    uid, _ = _new_user(db, made)
    assert _code(users.update_user, uid, users.UserUpdate(password="1234567"), db=db,
                 current_user=_admin())[0] == 400
    users.update_user(uid, users.UserUpdate(password="новый-пароль-2"), db=db, current_user=_admin())
    assert auth.verify_password("новый-пароль-2", db.get(User, uid).hashed_password)


def test_a_password_change_by_admin_lifts_the_login_lock_of_every_pair(db, made, audit):
    """Заблокированный по неверным попыткам человек получает новый пароль и должен войти сразу:
    замок снимается у почты и у всех её пар «почта | адрес» (см. test_login_lockout_targeting)."""
    uid, email = _new_user(db, made)
    norm = auth._norm_email(email)
    for key in (norm, auth._pair_key(norm, "203.0.113.5")):
        db.add(LoginAttempt(email=key, failed_count=3))
    db.commit()
    users.update_user(uid, users.UserUpdate(password="новый-пароль-3"), db=db, current_user=_admin())
    rows = db.query(LoginAttempt).filter(LoginAttempt.email.like(norm + "%")).all()
    assert rows and all(r.failed_count == 0 and r.locked_until is None for r in rows)


def test_notification_profile_validation_and_reset(db, made, audit):
    from app.notify.models import NotificationProfile
    prof = db.query(NotificationProfile).order_by(NotificationProfile.id).first()
    uid, _ = _new_user(db, made)
    assert _code(users.update_user, uid, users.UserUpdate(notification_profile_id=999999), db=db,
                 current_user=_admin())[0] == 400
    users.update_user(uid, users.UserUpdate(notification_profile_id=prof.id), db=db, current_user=_admin())
    assert db.get(User, uid).notification_profile_id == prof.id
    users.update_user(uid, users.UserUpdate(notification_profile_id=0), db=db, current_user=_admin())
    assert db.get(User, uid).notification_profile_id is None


# ── пользователи: удаление и списки ──────────────────────────────────────────

def test_delete_rules(db, made, audit):
    uid, _ = _new_user(db, made)
    assert _code(users.delete_user, 999999999, db=db, current_user=_admin())[0] == 404
    me = types.SimpleNamespace(id=uid, name="я")
    assert "самого себя" in _code(users.delete_user, uid, db=db, current_user=me)[1]
    assert "деактивируйте" in _code(users.delete_user, uid, db=db, current_user=_admin())[1]
    users.update_user(uid, users.UserUpdate(is_active=False), db=db, current_user=_admin())
    db.add(AuditLog(user_id=uid, user_name="Тест", action="zz_test_action"))
    db.commit()
    users.delete_user(uid, db=db, current_user=_admin())
    assert db.get(User, uid) is None
    row = db.query(AuditLog).filter(AuditLog.action == "zz_test_action").first()
    assert row is not None and row.user_id is None, "журнал должен остаться, отвязанный от пользователя"
    db.delete(row)
    db.commit()
    assert audit[-1][0] == "delete_user"


def test_list_users_and_profiles_and_access_overview(db, made):
    uid, email = _new_user(db, made)
    listing = users.list_users(db=db, current_user=_admin())
    mine = next(x for x in listing if x["id"] == uid)
    assert mine["email"] == email and mine["role"] == "viewer" and mine["is_active"] is True
    profiles = users.notification_profiles(db=db, current_user=_admin())
    assert profiles and {"id", "label", "is_default"} <= set(profiles[0])
    ov = users.access_overview(db=db, current_user=_admin())
    assert {"rows", "core", "outer", "shared_emails"} <= set(ov)
    assert ov["core"] == len([r for r in ov["rows"] if r["contour"] == "ядро"])
    assert any(r["email"] == email for r in ov["rows"])


def test_audit_log_filters(db, made):
    uid, _ = _new_user(db, made)
    db.add(AuditLog(user_id=uid, user_name="Тест ZZ", action="zz_audit_probe", details="проба 100% _ готово"))
    db.commit()
    try:
        out = users.get_audit_log(action="zz_audit_probe", db=db, current_user=_admin())
        assert out["total"] == 1 and out["items"][0]["user_id"] == uid
        assert users.get_audit_log(q="100% _", action="zz_audit_probe", db=db,
                                   current_user=_admin())["total"] == 1, "% и _ в поиске — обычные знаки"
        assert users.get_audit_log(q="100X", action="zz_audit_probe", db=db,
                                   current_user=_admin())["total"] == 0
        assert users.get_audit_log(user_id=uid, action="zz_audit_probe", db=db,
                                   current_user=_admin())["total"] == 1
        from datetime import date, timedelta
        today = date.today()
        assert users.get_audit_log(action="zz_audit_probe", date_from=today - timedelta(days=2),
                                   date_to=today + timedelta(days=2), db=db,
                                   current_user=_admin())["total"] == 1
        assert users.get_audit_log(action="zz_audit_probe", date_to=today - timedelta(days=5), db=db,
                                   current_user=_admin())["total"] == 0
    finally:
        db.query(AuditLog).filter(AuditLog.action == "zz_audit_probe").delete()
        db.commit()


# ── роли ─────────────────────────────────────────────────────────────────────

def _new_role(db, made, label=None):
    out = roles.create_role(roles.RoleCreate(label=label or f"zz роль {uuid.uuid4().hex[:6]}"),
                            db=db, current_user=_admin())
    made["roles"].append(out["id"])
    return out["id"]


def test_create_role_gets_a_key_and_a_row_for_every_section_with_nothing_allowed(db, made, audit):
    rid = _new_role(db, made)
    role = db.get(Role, rid)
    assert role.key == f"role_{rid}" and not role.is_system
    rows = db.query(RolePermission).filter(RolePermission.role_id == rid).all()
    assert {r.section for r in rows} == {s["key"] for s in SECTIONS}
    assert not any(r.can_view or r.can_edit or r.can_delete or r.can_create for r in rows)
    assert audit[-1][0] == "create_role"


def test_create_role_needs_a_label(db, audit):
    assert _code(roles.create_role, roles.RoleCreate(label="   "), db=db, current_user=_admin())[0] == 400


def test_list_roles_shows_admin_with_everything_and_a_new_role_with_nothing(db, made):
    rid = _new_role(db, made)
    out = roles.list_roles(db=db, current_user=_admin())
    by_key = {r["key"]: r for r in out["roles"]}
    assert all(all(v for v in p.values()) for p in by_key["admin"]["permissions"].values())
    new = next(r for r in out["roles"] if r["id"] == rid)
    assert not any(any(p.values()) for p in new["permissions"].values())
    assert new["staff_group"] == "" and new["is_master"] is False and new["user_count"] == 0
    assert out["sections"] == SECTIONS


def test_update_role_label_group_and_master(db, made, audit):
    rid = _new_role(db, made)
    roles.update_role(rid, roles.RoleUpdate(label="zz переименована", staff_group="traffic", is_master=True),
                      db=db, current_user=_admin())
    r = db.get(Role, rid)
    assert (r.label, r.staff_group, r.is_master) == ("zz переименована", "traffic", True)
    roles.update_role(rid, roles.RoleUpdate(staff_group="чепуха"), db=db, current_user=_admin())
    assert db.get(Role, rid).staff_group is None, "неизвестная рабочая группа снимается"
    assert audit[-1][0] == "update_role"


def test_update_role_permissions_only_touch_actions_the_section_offers(db, made, audit):
    rid = _new_role(db, made)
    view_only = next(s["key"] for s in SECTIONS if s["actions"] == ["view"])
    with_delete = next(s["key"] for s in SECTIONS if "delete" in s["actions"])
    no_delete = next(s["key"] for s in SECTIONS if "edit" in s["actions"] and "delete" not in s["actions"])
    roles.update_role(rid, roles.RoleUpdate(permissions=[
        roles.PermissionInput(section=view_only, can_view=True, can_edit=True, can_delete=True),
        roles.PermissionInput(section=with_delete, can_view=True, can_edit=True, can_delete=True),
        roles.PermissionInput(section=no_delete, can_view=True, can_edit=True, can_delete=True),
        roles.PermissionInput(section="no_such_section", can_view=True),
    ]), db=db, current_user=_admin())

    def row(sec):
        return db.query(RolePermission).filter(RolePermission.role_id == rid, RolePermission.section == sec).one()
    assert (row(view_only).can_view, row(view_only).can_edit, row(view_only).can_delete) == (1, 0, 0)
    assert (row(with_delete).can_edit, row(with_delete).can_delete) == (1, 1)
    assert (row(no_delete).can_edit, row(no_delete).can_delete) == (1, 0), \
        "право «удаление» не выдаётся разделу, у которого такого действия нет"
    assert not db.query(RolePermission).filter(RolePermission.role_id == rid,
                                               RolePermission.section == "no_such_section").first()


def test_update_role_none_means_untouched_and_false_means_off(db, made, audit):
    rid = _new_role(db, made)
    sec = next(s["key"] for s in SECTIONS if "delete" in s["actions"])
    roles.update_role(rid, roles.RoleUpdate(permissions=[
        roles.PermissionInput(section=sec, can_view=True, can_edit=True, can_delete=True)]),
        db=db, current_user=_admin())
    roles.update_role(rid, roles.RoleUpdate(permissions=[
        roles.PermissionInput(section=sec, can_delete=False)]), db=db, current_user=_admin())
    r = db.query(RolePermission).filter(RolePermission.role_id == rid, RolePermission.section == sec).one()
    assert (r.can_view, r.can_edit, r.can_delete) == (1, 1, 0), "правку присылать не нужно: её не трогают"


def test_scope_is_written_only_for_scoped_sections_and_garbage_becomes_all(db, made, audit):
    rid = _new_role(db, made)
    roles.update_role(rid, roles.RoleUpdate(permissions=[
        roles.PermissionInput(section="sales_registry", can_view=True, deals_scope="own"),
        roles.PermissionInput(section="year_plan", can_view=True, deals_scope="мусор"),
        roles.PermissionInput(section="contracts", can_view=True, deals_scope="own"),
    ]), db=db, current_user=_admin())

    def scope(sec):
        return db.query(RolePermission).filter(RolePermission.role_id == rid,
                                               RolePermission.section == sec).one().deals_scope
    assert scope("sales_registry") == "own"
    assert scope("year_plan") == "all"
    assert scope("contracts") != "own", "у не-продажных разделов область не пишется"


def test_the_admin_role_and_unknown_roles_cannot_be_updated(db, audit):
    admin = db.query(Role).filter(Role.key == "admin").one()
    admin_id, label_before = admin.id, admin.label
    try:
        assert _code(roles.update_role, admin_id, roles.RoleUpdate(label="x"), db=db,
                     current_user=_admin())[0] == 400
        assert _code(roles.update_role, 999999999, roles.RoleUpdate(label="x"), db=db,
                     current_user=_admin())[0] == 404
    finally:
        # Попытка переименовать роль админа не должна оставить следа на базе, на которой идёт прогон:
        # 07.10.2026 на стенде у роли осталось название «x» и показывалось в меню профиля владельца.
        db.rollback()
        now = db.query(Role).filter(Role.id == admin_id).one()
        if now.label != label_before:
            changed_to, now.label = now.label, label_before
            db.commit()
            raise AssertionError(f"название роли admin изменилось: {label_before!r} → {changed_to!r} (возвращено)")


def test_delete_role_rules(db, made, audit):
    system = db.query(Role).filter(Role.is_system == 1).first()
    code, msg = _code(roles.delete_role, system.id, db=db, current_user=_admin())
    assert code == 400 and "системную" in msg, "системную роль нельзя удалить именно потому, что она системная"
    assert _code(roles.delete_role, 999999999, db=db, current_user=_admin())[0] == 404
    rid = _new_role(db, made)
    uid, _ = _new_user(db, made, role=f"role_{rid}")
    assert "используется" in _code(roles.delete_role, rid, db=db, current_user=_admin())[1]
    db.query(User).filter(User.id == uid).delete()
    db.commit()
    roles.delete_role(rid, db=db, current_user=_admin())
    assert db.get(Role, rid) is None
    assert not db.query(RolePermission).filter(RolePermission.role_id == rid).count()
    assert audit[-1][0] == "delete_role"
