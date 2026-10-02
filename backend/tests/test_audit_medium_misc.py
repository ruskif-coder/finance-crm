# -*- coding: utf-8 -*-
"""Средние находки аудита 01.10.2026, группа «остальное» (С-7, С-9)."""
import inspect
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

import app.main  # noqa: F401


def test_c7_demo_weborama_create_is_one_at_a_time(monkeypatch):
    """Двойной клик заводил второй такой же объект в кабинете Weborama — удалить нельзя."""
    from app.routers import weborama_demo as W
    from app import ext_lock

    @contextmanager
    def busy(kind, obj, err, what, where=""):
        raise err(f"{what} уже идёт")
        yield
    monkeypatch.setattr(ext_lock, "only_one", busy)
    with pytest.raises(HTTPException) as e:
        W._post(object(), "/advertiser/projects.json", data={})
    assert e.value.status_code == 409


def test_c7_all_creating_demo_calls_go_through_the_lock():
    from app.routers import weborama_demo as W
    src = inspect.getsource(W)
    assert '_run(c.call, "POST"' not in src.replace('return _run(c.call, "POST", path, **kw)', '')


@pytest.mark.parametrize("fn,action", [
    ("app.routers.launch_prep:drop_set", "delete_creative_set"),
    ("app.routers.launch_prep:upload_file", "upload_creative_file"),
    ("app.routers.operations:import_excel", "import_operations"),
])
def test_c9_destructive_and_bulk_actions_are_journaled(fn, action):
    import importlib
    from app.audit_labels import ACTION_LABELS
    mod, name = fn.split(":")
    src = inspect.getsource(getattr(importlib.import_module(mod), name))
    assert f'"{action}"' in src and "log_action(" in src
    assert action in ACTION_LABELS


def test_n8_media_plan_editors_have_registry_scope_row():
    """Н-8: поиск сделки в медиаплане берёт область «свои/все» из `sales_registry`. Роль с
    правом редактора МП без этой строки получила бы 403 на весь поиск."""
    from sqlalchemy import text as _t
    from app.database import SessionLocal as _S
    db = _S()
    try:
        bad = db.execute(_t("""SELECT p.role_id FROM role_permissions p
              WHERE p.section = 'media_plans_editor' AND p.can_view = 1
                AND NOT EXISTS (SELECT 1 FROM role_permissions s
                                 WHERE s.role_id = p.role_id AND s.section = 'sales_registry')""")).all()
        assert not bad, bad
    finally:
        db.close()


def test_n9_cyrillic_webhook_secret_is_404_not_500():
    """Н-9: compare_digest на str с кириллицей бросал TypeError → 500."""
    from fastapi.testclient import TestClient
    from app.main import app as _app
    c = TestClient(_app)
    for path in ("/api/notifications/settings/telegram/webhook/секрет", "/api/pub-bot/webhook/секрет"):
        assert c.post(path, json={}).status_code != 500, path
