# -*- coding: utf-8 -*-
"""Предпросмотр креатива в «Подвисших» (владелец 29.10.2026): менеджеру паблишеров без права на креативы — только то,
что уже отправлено площадке; черновики сборки не открываются."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.main import app
from app.routers.auth import get_current_user


class _Role:
    def __init__(self, key):
        self.key, self.id, self.staff_group, self.is_master = key, None, None, False


class _User:
    def __init__(self, key):
        db = SessionLocal()
        try:
            rid = db.execute(text("SELECT id FROM roles WHERE key = :k"), {"k": key}).scalar()
        finally:
            db.close()
        self.id, self.name, self.email = None, "test", "t@t"
        self.role, self.role_id, self.consent_accepted_at = _Role(key), rid, True


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _set(sent: bool):
    db = SessionLocal()
    try:
        cond = "EXISTS" if sent else "NOT EXISTS"
        return db.execute(text(f"""
            SELECT cs.id, (SELECT f.id FROM launch_prep_creative_file f WHERE f.set_id = cs.id ORDER BY f.id LIMIT 1)
              FROM launch_prep_creative_set cs
             WHERE EXISTS (SELECT 1 FROM launch_prep_creative_file f WHERE f.set_id = cs.id)
               AND {cond} (SELECT 1 FROM launch_prep_pair p WHERE p.set_id = cs.id AND p.sent_at IS NOT NULL)
             ORDER BY cs.id DESC LIMIT 1""")).first()
    finally:
        db.close()


def test_publisher_manager_sees_files_of_a_sent_creative(client, monkeypatch):
    row = _set(True)
    if not row:
        pytest.skip("на стенде нет отправленного креатива с файлом")
    # Файлов копии прода в хранилище стенда почти нет — отдачу с диска подменяем; проверка «отправлен ли» и права — настоящие.
    from fastapi.responses import PlainTextResponse
    from app.routers import launch_prep as LP
    monkeypatch.setattr(LP, "file_response", lambda rec: PlainTextResponse(f"file {rec.id}"))
    app.dependency_overrides[get_current_user] = lambda: _User("role_10")       # менеджер паблишеров
    r = client.get(f"/api/publisher-approvals/set/{row[0]}/files")
    assert r.status_code == 200 and row[1] in [f["id"] for f in r.json()["files"]]
    got = client.get(f"/api/publisher-approvals/file/{row[1]}")
    assert got.status_code == 200 and got.text == f"file {row[1]}"


def test_unsent_creative_is_not_opened(client):
    row = _set(False)
    if not row:
        pytest.skip("на стенде нет неотправленного креатива с файлом")
    app.dependency_overrides[get_current_user] = lambda: _User("role_10")
    assert client.get(f"/api/publisher-approvals/set/{row[0]}/files").status_code == 404
    assert client.get(f"/api/publisher-approvals/file/{row[1]}").status_code == 404


def test_closed_without_the_approvals_right(client):
    app.dependency_overrides[get_current_user] = lambda: _User("role_11")
    assert client.get("/api/publisher-approvals/set/1/files").status_code == 403
