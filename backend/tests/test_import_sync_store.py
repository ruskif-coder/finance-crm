# -*- coding: utf-8 -*-
"""Сессия импорта операций видна ДРУГОМУ процессу бэкенда (03.11.2026, `--workers`).

Поломка, которую ловит: сессия preview→apply в словаре памяти процесса. С несколькими процессами «Применить» попадает
в соседний, и человек на только что разобранный файл получает «Сессия импорта истекла или не найдена».
"""
import subprocess
import sys
import uuid
from datetime import datetime

import pytest

from app.import_sync_store import FileStore
from app.routers import operations as ops


def test_session_written_here_is_read_by_another_process():
    key = uuid.uuid4().hex
    ops.IMPORT_SYNC_CACHE[key] = {"rows": [{"status": "new", "key": "k1"}], "created_at": datetime.utcnow(), "user_id": 7}
    try:
        from app import import_sync_store
        code = (f"import app.import_sync_store as S; S.DIR = {import_sync_store.DIR!r}; "
                f"from app.routers import operations as o; s = o.IMPORT_SYNC_CACHE.get('{key}'); "
                "print(s and s['user_id'], s and s['rows'][0]['key'])")
        out = subprocess.run([sys.executable, "-c", code], cwd="/app", capture_output=True, text=True, timeout=120)
        assert out.stdout.strip().splitlines()[-1] == "7 k1", out.stderr[-500:]
    finally:
        ops.IMPORT_SYNC_CACHE.pop(key)
    assert key not in ops.IMPORT_SYNC_CACHE


def test_key_from_the_request_cannot_leave_the_folder():
    s = FileStore()
    for bad in ("../../etc/passwd", "a/b", "", "Z" * 10):
        assert s.get(bad) is None
        with pytest.raises(KeyError):
            s[bad] = {}


def test_pop_of_a_session_removed_by_a_neighbour_is_quiet():
    s = FileStore()
    assert s.pop(uuid.uuid4().hex) is None
