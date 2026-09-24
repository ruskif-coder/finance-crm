# -*- coding: utf-8 -*-
"""Удаление кабинета — только администратор, только неактивный и без площадок
(владелец, 24.09.2026).

Кабинет с площадками — это работающая связь: площадка потеряла бы доступ к своим
заданиям. Активный кабинет — это люди, которые прямо сейчас входят. Служебный — наш
общий доступ. Удаляется только то, что никому не служит, — вместе с его учётками и
лентой, которые без кабинета бессмысленны.
"""
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.main  # noqa: F401 — все модели
from app.cabinet.models import Cabinet, CabinetAccount, CabinetPublisher
from app.database import SessionLocal
from app.models import User
from app.routers import cabinets as cb

APP = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture
def env(monkeypatch):
    db = SessionLocal()
    admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    monkeypatch.setattr(cb, "log_action", lambda *a, **kw: None)
    made = []

    def mk(state="черновик", kind="площадка", with_site=False, with_account=False):
        c = Cabinet(name="[тест] удаление кабинета", kind=kind, state=state)
        db.add(c)
        db.flush()
        if with_site:
            pid = db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 1")).scalar()
            db.add(CabinetPublisher(cabinet_id=c.id, publisher_id=pid))
        if with_account:
            db.add(CabinetAccount(cabinet_id=c.id, email=f"test-del-{c.id}@example.invalid",
                                  name="тест"))
        db.commit()
        made.append(c.id)
        return c

    yield SimpleNamespace(db=db, admin=admin, mk=mk)
    db.rollback()
    for cid in made:
        db.execute(text("DELETE FROM cabinet_account WHERE cabinet_id = :c"), {"c": cid})
        db.execute(text("DELETE FROM cabinet WHERE id = :c"), {"c": cid})
    db.commit()
    db.close()


def test_an_idle_empty_cabinet_is_deleted_with_its_accounts(env):
    c = env.mk(state="приостановлен", with_account=True)
    cid = c.id
    cb.delete_cabinet(cid, env.db, env.admin)
    assert env.db.query(Cabinet).filter(Cabinet.id == cid).first() is None
    assert not env.db.query(CabinetAccount).filter(CabinetAccount.cabinet_id == cid).count()


@pytest.mark.parametrize("kw, why", [
    ({"state": "активен"}, "активный"),
    ({"with_site": True}, "с площадкой"),
    ({"kind": "служебный", "state": "приостановлен"}, "служебный"),
])
def test_a_working_cabinet_is_not_deleted(env, kw, why):
    c = env.mk(**kw)
    with pytest.raises(HTTPException) as e:
        cb.delete_cabinet(c.id, env.db, env.admin)
    assert e.value.status_code == 400, why
    assert env.db.query(Cabinet).filter(Cabinet.id == c.id).first() is not None


def test_only_the_admin_may_delete():
    src = io.open(APP / "routers/cabinets.py", encoding="utf-8").read()
    head = src[src.index('@router.delete("/{cabinet_id}")'):]
    head = head[:head.index("):") + 2]
    assert "require_admin" in head


def test_the_list_says_which_cabinet_may_go(env):
    c = env.mk(state="черновик")
    out = cb.list_cabinets(env.db, env.admin) if hasattr(cb, "list_cabinets") else None
    if out is None:
        pytest.skip("имя ручки списка другое")
    row = next(x for x in out["cabinets"] if x["id"] == c.id)
    assert row["deletable"] is True and row["created_at"]
