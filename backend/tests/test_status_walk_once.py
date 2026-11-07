# -*- coding: utf-8 -*-
"""«Состояние системы» обходило хранилище файлов ДВАЖДЫ за открытие — для «Хранилища» и для «Сирот» (07.11.2026, замер
скорости: 2 × 2,2 с из 4,6 с экрана). Теперь один обход на открытие; результат обхода — тот же словарь {путь: размер}."""
import os

import app.model_registry  # noqa: F401
from app.system import status as ST


def test_uploads_are_walked_once_per_screen(monkeypatch):
    calls = []
    real = ST._scan_uploads
    monkeypatch.setattr(ST, "_scan_uploads", lambda: calls.append(1) or real())
    ST._UPLOADS_CACHE.clear()
    ST.check_storage(None)
    ST._walk_uploads()
    assert len(calls) == 1


def test_scan_finds_the_same_files_as_os_walk(tmp_path, monkeypatch):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "x.txt").write_bytes(b"12345")
    (tmp_path / "y.bin").write_bytes(b"1")
    monkeypatch.setattr(ST, "UPLOADS_ROOT", str(tmp_path))
    ST._UPLOADS_CACHE.clear()
    want = {os.path.relpath(os.path.join(r, n), tmp_path).replace("\\", "/"): os.path.getsize(os.path.join(r, n))
            for r, _, ns in os.walk(tmp_path) for n in ns}
    assert ST._scan_uploads() == want == {"a/b/x.txt": 5, "y.bin": 1}
