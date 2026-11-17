"""Закреплённые и недавние экраны меню (навигация v3, хендофф 17.11.2026): хранятся у пользователя, лимиты 3 и 12.

Пишет только своего временного пользователя; строка настроек уходит вместе с ним (ON DELETE CASCADE).
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.notify.models  # noqa: F401  — FK users → notification_profiles
from app import nav_prefs
from app.database import SessionLocal
from app.models import Role, User


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.execute(text("DELETE FROM users WHERE email LIKE 't-nav-%@example.invalid'"))
    s.commit()
    s.close()


def mkuser(db, tag):
    u = User(email=f"t-nav-{tag}@example.invalid", name="прибор меню", hashed_password="x",
             role_id=db.query(Role.id).order_by(Role.id).first()[0])
    db.add(u)
    db.commit()
    return u.id


def test_without_a_row_operations_is_pinned_by_default(db):
    """Поломка: пустой список по умолчанию — README: «По умолчанию закреплён Финансы → Операции»."""
    uid = mkuser(db, "a")
    assert nav_prefs.read(db, uid) == {"pinned": ["/finance/operations"], "recent": []}


def test_saved_prefs_come_back_and_belong_to_one_user(db):
    """Поломка: настройки пишутся без user_id в условии — второй пользователь видит чужие закреплённые."""
    a, b = mkuser(db, "a"), mkuser(db, "b")
    nav_prefs.save(db, a, ["/traffic/dashboard", "/sales/deals"], ["/sales/deals", "/finance/pnl"])
    assert nav_prefs.read(db, a) == {"pinned": ["/traffic/dashboard", "/sales/deals"],
                                     "recent": ["/sales/deals", "/finance/pnl"]}
    nav_prefs.save(db, a, [], ["/finance/pnl"])
    assert nav_prefs.read(db, a) == {"pinned": [], "recent": ["/finance/pnl"]}
    assert nav_prefs.read(db, b)["pinned"] == ["/finance/operations"]


def test_fourth_pin_is_refused(db):
    """Поломка: лимит три держит только фронт — ручкой можно закрепить сколько угодно."""
    uid = mkuser(db, "a")
    with pytest.raises(HTTPException) as e:
        nav_prefs.save(db, uid, ["/a", "/b", "/c", "/d"], [])
    assert e.value.status_code == 422


def test_recent_is_deduplicated_and_cut_to_twelve(db):
    """Поломка: недавние растут без конца и с дублями — подвал «недавно» показывает один экран дважды."""
    uid = mkuser(db, "a")
    many = [f"/s/{i}" for i in range(15)]
    nav_prefs.save(db, uid, [], ["/s/0"] + many)
    got = nav_prefs.read(db, uid)["recent"]
    assert got == [f"/s/{i}" for i in range(12)]


@pytest.mark.parametrize("bad", ["https://evil.example/x", "//evil.example", "javascript:alert(1)", "", "/" + "x" * 300])
def test_only_internal_addresses_are_kept(db, bad):
    """Поломка: в закреплённые попадает внешний адрес — меню уводит с сайта (кнопка закрепа строит href из строки)."""
    uid = mkuser(db, "a")
    with pytest.raises(HTTPException) as e:
        nav_prefs.save(db, uid, [bad], [])
    assert e.value.status_code == 422
