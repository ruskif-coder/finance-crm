# -*- coding: utf-8 -*-
"""Тема интерфейса хранится у пользователя (владелец 22.10.2026: «да, давай поле»): День · Ночь · Графит
ходят за человеком на любое устройство. Пишет только свою, любой вошедший; чужое значение — 422."""
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, get_db
from app.main import app
from app.models import User
from app.routers.auth import get_current_user, get_current_user_any


@pytest.fixture()
def me():
    db = SessionLocal()
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    was = db.execute(text("SELECT theme FROM users WHERE id = :i"), {"i": u.id}).scalar()
    uid = u.id
    db.close()

    # Пользователь — из той же сессии, что у ручки (как в настоящем get_current_user_any), иначе её commit
    # не видит правку.
    def current(db=Depends(get_db)):
        return db.get(User, uid)
    app.dependency_overrides[get_current_user] = current
    app.dependency_overrides[get_current_user_any] = current
    yield uid
    app.dependency_overrides.clear()
    db = SessionLocal()
    db.execute(text("UPDATE users SET theme = :t WHERE id = :i"), {"t": was, "i": uid})
    db.commit()
    db.close()


def _theme(uid):
    db = SessionLocal()
    try:
        return db.execute(text("SELECT theme FROM users WHERE id = :i"), {"i": uid}).scalar()
    finally:
        db.close()


@pytest.mark.parametrize("theme", ["dark", "graphite", "pink", "japandi", "light"])
def test_theme_is_saved_and_returned_by_me(me, theme):
    c = TestClient(app)
    r = c.put("/api/auth/me/theme", json={"theme": theme})
    assert r.status_code == 200, r.text
    assert _theme(me) == theme
    assert c.get("/api/auth/me").json()["theme"] == theme


def test_unknown_theme_is_rejected(me):
    r = TestClient(app).put("/api/auth/me/theme", json={"theme": "neon"})
    assert r.status_code == 422


def test_column_has_check_constraint():
    db = SessionLocal()
    try:
        got = db.execute(text("""SELECT 1 FROM pg_constraint WHERE conname = 'ck_users_theme'""")).scalar()
    finally:
        db.close()
    assert got == 1
