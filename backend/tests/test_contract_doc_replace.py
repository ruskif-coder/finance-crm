# -*- coding: utf-8 -*-
"""Замена документа договора не теряет прежний (аудит 2.6.76, п. 1.3; живо в 2.7.0, сделано 22.10.2026).

Ручка стирала старый файл ДО проверки нового: отклонённый (415/413) — и документа нет, а ссылка в базе осталась.
Второй путь к той же потере — новый с тем же именем ложится поверх, и «уборка старого» удаляет уже новый.
Образец — договоры площадок (`test_publisher_contract_doc_replace`)."""
import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.routers import contracts as C


class _Db:
    def __init__(self, c):
        self.c = c

    def query(self, model):
        c = self.c
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: c))

    def commit(self):
        pass


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(C, "log_action", lambda *a, **kw: None)
    old = "7_dogovor.pdf"
    (tmp_path / old).write_bytes(b"%PDF old")
    c = SimpleNamespace(id=7, attached_filename=old)
    return SimpleNamespace(root=tmp_path, c=c, db=_Db(c), old=old, user=SimpleNamespace(id=1))


def _upload(w, name, data):
    return asyncio.run(C.upload_contract_document(7, UploadFile(file=io.BytesIO(data), filename=name), w.db, w.user))


def test_rejected_type_keeps_the_old_document(wired):
    with pytest.raises(HTTPException) as e:
        _upload(wired, "virus.exe", b"MZ")
    assert e.value.status_code == 415
    assert (wired.root / wired.old).read_bytes() == b"%PDF old"
    assert wired.c.attached_filename == wired.old


def test_too_big_keeps_the_old_document(wired, monkeypatch):
    monkeypatch.setattr(C, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(HTTPException) as e:
        _upload(wired, "new.pdf", b"%PDF too big")
    assert e.value.status_code == 413
    assert (wired.root / wired.old).read_bytes() == b"%PDF old"


def test_same_name_replacement_leaves_the_new_file(wired):
    _upload(wired, "dogovor.pdf", b"%PDF new")
    assert (wired.root / wired.old).read_bytes() == b"%PDF new"


def test_other_name_replaces_and_removes_the_old(wired):
    _upload(wired, "dop.pdf", b"%PDF new")
    assert wired.c.attached_filename == "7_dop.pdf"
    assert (wired.root / "7_dop.pdf").read_bytes() == b"%PDF new"
    assert not (wired.root / wired.old).exists()
