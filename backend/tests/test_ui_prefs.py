"""Личные настройки вида таблиц (19.11.2026): колонки таблицы площадок в расхлопе дашборда трафика.

Пишет только своих временных пользователей; строки настроек уходят вместе с ними (ON DELETE CASCADE).
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.notify.models  # noqa: F401  — FK users → notification_profiles
from app import ui_prefs
from app.database import SessionLocal
from app.models import Role, User

KEY = "traffic.sites.columns"


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.execute(text("DELETE FROM users WHERE email LIKE 't-uip-%@example.invalid'"))
    s.commit()
    s.close()


def mkuser(db, tag):
    u = User(email=f"t-uip-{tag}@example.invalid", name="прибор вида", hashed_password="x",
             role_id=db.query(Role.id).order_by(Role.id).first()[0])
    db.add(u)
    db.commit()
    return u.id


def test_without_a_row_value_is_none(db):
    """Поломка: без сохранённой настройки отдаётся пустой список — у человека пропадают все колонки."""
    assert ui_prefs.read(db, mkuser(db, "a"), KEY) is None


def test_saved_value_comes_back_and_belongs_to_one_user(db):
    """Поломка: запись без user_id в условии — второй трафик видит чужой набор колонок."""
    a, b = mkuser(db, "a"), mkuser(db, "b")
    v = {"order": ["fact", "plan", "cr"], "hidden": ["wr"]}
    ui_prefs.save(db, a, KEY, v)
    assert ui_prefs.read(db, a, KEY) == v
    ui_prefs.save(db, a, KEY, {"order": [], "hidden": []})
    assert ui_prefs.read(db, a, KEY) == {"order": [], "hidden": []}
    assert ui_prefs.read(db, b, KEY) is None


def test_unknown_key_is_refused(db):
    """Поломка: ручка пишет любой ключ — таблица превращается в склад произвольного JSON."""
    with pytest.raises(HTTPException) as e:
        ui_prefs.save(db, mkuser(db, "a"), "anything", {"x": 1})
    assert e.value.status_code == 404


@pytest.mark.parametrize("bad", [
    {"order": ["fact", "fact"], "hidden": []},          # дубль
    {"order": ["name"], "hidden": []},                  # «Площадка» не настраивается — она закреплена
    {"order": ["fact"], "hidden": ["nope"]},            # такой колонки нет
    {"order": "fact", "hidden": []},                    # не список
    ["fact"],                                           # не та форма
])
def test_bad_columns_value_is_refused(db, bad):
    """Поломка: проверка формы только на фронте — ручкой можно записать то, от чего таблица упадёт."""
    with pytest.raises(HTTPException) as e:
        ui_prefs.save(db, mkuser(db, "a"), KEY, bad)
    assert e.value.status_code == 422
