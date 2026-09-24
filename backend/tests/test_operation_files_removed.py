# -*- coding: utf-8 -*-
"""Удаление операции убирает и её сканы с диска (аудит 23.09.2026, этап 8.7).

Строки `operation_files` уходят каскадом базы, а файлы оставались: каждый удалённый скан
— сирота на диске навсегда. Три пути удаления — одиночное, массовое и принудительное
(материнская с паролем) — и каждый обязан убрать файлы ПОСЛЕ записи в базу: откат
не должен оставить строку без файла.
"""
import os
from datetime import date
from types import SimpleNamespace

import pytest

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.models import Operation, OperationFile, User
from app.routers import operation_chains as chains
from app.routers import operations as ops

ROOT = os.path.join(ops.UPLOADS_ROOT, ops.OP_FILES_SUBDIR)


@pytest.fixture
def env(monkeypatch):
    db = SessionLocal()
    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    made = []
    monkeypatch.setattr(ops, "log_action", lambda *a, **kw: None)
    monkeypatch.setattr(chains, "log_action", lambda *a, **kw: None)
    monkeypatch.setattr(chains, "confirm_password", lambda *a, **kw: None)

    def mk():
        op = Operation(date=date(2026, 9, 1), status="ПЛАН ОПЛАТ", income=0, expense=1,
                       period="2026-09", description="[тест] скан")
        db.add(op)
        db.flush()
        os.makedirs(ROOT, exist_ok=True)
        name = f"op{op.id}_test_scan.pdf"
        full = os.path.join(ROOT, name)
        with open(full, "wb") as fh:
            fh.write(b"%PDF-test")
        db.add(OperationFile(operation_id=op.id, path=f"{ops.OP_FILES_SUBDIR}/{name}",
                             original_name="скан.pdf", size_bytes=9))
        db.commit()
        made.append(full)
        return op, full

    yield SimpleNamespace(db=db, user=user, mk=mk)
    db.rollback()
    for full in made:
        if os.path.exists(full):
            os.remove(full)
    db.query(Operation).filter(Operation.description == "[тест] скан").delete()
    db.commit()
    db.close()


def test_single_delete_removes_the_scan(env):
    op, full = env.mk()
    ops.delete_operation(op.id, env.db, env.user)
    assert not os.path.exists(full), "скан остался на диске"


def test_bulk_delete_removes_the_scans(env):
    (a, fa), (b, fb) = env.mk(), env.mk()
    ops.bulk_delete_operations(ops.OperationBulkDelete(ids=[a.id, b.id]), env.db, env.user)
    assert not os.path.exists(fa) and not os.path.exists(fb)


def test_force_delete_removes_the_scan(env):
    op, full = env.mk()
    chains.force_delete(op.id, chains.ForceDeleteIn(password="x"), env.db, env.user)
    assert not os.path.exists(full)
