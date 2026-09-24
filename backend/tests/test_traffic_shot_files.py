# -*- coding: utf-8 -*-
"""Скриншоты размещения: удаление работает, загрузка не перезаписывает чужой файл.

Аудит 23.09.2026:
  4.M1 — удаление скриншота всегда отвечало 500: ручка читала `rec.filename`, а у строки
         такого поля нет (`original_name`). Ошибочно приложенный скриншот убрать было нельзя.
  4.L1 — номер в имени файла брался как «сколько уже есть + 1». Удалили первый из двух —
         третий получает номер второго и молча его перезаписывает.

Ручки вызываются напрямую, база подменена: проверяется работа с файлами и то, что
ручка не падает, а не ORM.
"""
import asyncio
import io
import os
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile

from app.routers import traffic as T
from app.traffic import files as tfiles

PAIR = 999480


class _Q:
    def __init__(self, db):
        self.db = db

    def filter(self, *a):
        return self

    def count(self):
        return self.db.count

    def first(self):
        return self.db.rec


class _Db:
    def __init__(self, count=0, rec=None):
        self.count, self.rec = count, rec
        self.added, self.deleted = [], []

    def query(self, model):
        return _Q(self)

    def add(self, r):
        self.added.append(r)

    def delete(self, r):
        self.deleted.append(r)

    def commit(self):
        pass


@pytest.fixture
def wired(monkeypatch, tmp_path):
    deal = SimpleNamespace(id=1, code="HCLA6E")
    pub = SimpleNamespace(code="SMK1")
    s = SimpleNamespace(no=2)
    monkeypatch.setattr(T, "_pair_in_scope",
                        lambda db, pid, u: (SimpleNamespace(id=pid), s, None, pub, deal))
    monkeypatch.setattr(T, "UPLOADS_ROOT", str(tmp_path))
    monkeypatch.setattr(T, "log_action", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_shot_out", lambda rec: {"path": rec.path})
    return SimpleNamespace(root=tmp_path, user=SimpleNamespace(id=1, name="трафик"))


def _upload(db, wired, data=b"%PDF-1.4 new"):
    f = UploadFile(file=io.BytesIO(data), filename="shot.pdf")
    return asyncio.run(T.upload_shot(PAIR, f, db, wired.user))


def test_deleting_a_screenshot_works(wired, monkeypatch):
    removed = []
    monkeypatch.setattr(T, "remove_upload", lambda rel: removed.append(rel))
    rec = SimpleNamespace(path="shots/p1_x.webp", original_name="скрин.png", pair_id=PAIR)
    db = _Db(rec=rec)

    T.drop_shot(1, db, wired.user)

    assert db.deleted == [rec]
    assert removed == ["shots/p1_x.webp"]


def test_upload_after_a_deletion_does_not_overwrite(wired):
    """Были №1 и №2, №1 удалили: в базе одна строка, а файл №2 на месте."""
    name2 = tfiles.traffic_file_name("HCLA6E", "SMK1", 2, 2, ".pdf")
    shots = wired.root / T.SHOTS_DIR
    shots.mkdir()
    kept = shots / f"p{PAIR}_{name2}"
    kept.write_bytes(b"%PDF-1.4 old")

    db = _Db(count=1)
    out = _upload(db, wired)

    assert kept.read_bytes() == b"%PDF-1.4 old", "загрузка перезаписала соседний скриншот"
    assert out["path"] != f"{T.SHOTS_DIR}/p{PAIR}_{name2}"
    assert os.path.exists(os.path.join(wired.root, out["path"]))
