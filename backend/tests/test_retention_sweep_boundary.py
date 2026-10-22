# -*- coding: utf-8 -*-
"""Уборка по срокам стирает только внутри хранилища (аудит 2.6.76, п. 1.7; сделано 22.10.2026)."""
import importlib

sweep = importlib.import_module("scripts.2026-08-30_retention_sweep")


def test_path_outside_storage_is_not_touched(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("не трогать")
    assert sweep.wipe("../secret.txt", "file", root=str(root)) is False
    assert outside.exists()


def test_file_and_dir_inside_storage_are_wiped(tmp_path):
    root = tmp_path / "uploads"
    (root / "lp" / "box").mkdir(parents=True)
    (root / "lp" / "a.zip").write_bytes(b"x")
    (root / "lp" / "box" / "i.html").write_text("x")
    assert sweep.wipe("lp/a.zip", "file", root=str(root)) is True
    assert sweep.wipe("lp/box", "dir", root=str(root)) is True
    assert not (root / "lp" / "a.zip").exists() and not (root / "lp" / "box").exists()


def test_missing_file_is_not_an_error(tmp_path):
    assert sweep.wipe("lp/none.zip", "file", root=str(tmp_path)) is False
