# -*- coding: utf-8 -*-
"""Скриншоты пары: трафик видит всё (очередь общая, 03.09.2026), аккаунт — только свои
сделки (аудит 01.10.2026, К-4). Файл открывался и по праву «креативы» по номеру — аккаунт
доставал скриншоты чужой сделки перебором id."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal
from app.routers import traffic as T


@pytest.fixture
def shot():
    db = SessionLocal()
    r = db.execute(text("SELECT f.id, f.pair_id FROM launch_prep_pair_file f ORDER BY f.id LIMIT 1")).first()
    if not r:
        db.close()
        pytest.skip("нет скриншотов на стенде")
    from app.models import User
    u = db.execute(text("SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id "
                        "WHERE r.key = 'admin' LIMIT 1")).scalar()
    yield db, r[0], r[1], db.get(User, u)
    db.close()


def _as(monkeypatch, traffic: bool):
    from app import permissions
    monkeypatch.setattr(permissions, "get_permissions_for_user", lambda db, u: {
        "traffic_queue": {"view": traffic}, "creatives": {"view": True}})
    monkeypatch.setattr(T, "get_permissions_for_user", permissions.get_permissions_for_user, raising=False)


def test_account_cannot_open_someone_elses_shot(shot, monkeypatch):
    db, fid, pid, user = shot
    _as(monkeypatch, traffic=False)
    from app.routers import launch_prep as lp

    def deny(db_, u, deal):
        raise HTTPException(404, "Сделка не найдена")
    monkeypatch.setattr(lp, "_assert_deal_in_scope", deny)
    with pytest.raises(HTTPException) as e:
        T.get_shot(fid, db=db, current_user=user)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        T.files_archive(pid, db=db, current_user=user)
    with pytest.raises(HTTPException):
        T.list_files(pid, db=db, current_user=user)


def test_traffic_is_not_limited_by_deal_scope(shot, monkeypatch):
    db, fid, pid, user = shot
    _as(monkeypatch, traffic=True)
    from app.routers import launch_prep as lp
    called = []
    monkeypatch.setattr(lp, "_assert_deal_in_scope", lambda *a: called.append(1))
    try:
        T.get_shot(fid, db=db, current_user=user)
    except HTTPException as e:
        assert e.detail != "Сделка не найдена"   # файла на стенде может не быть
    assert not called
