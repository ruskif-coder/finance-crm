# -*- coding: utf-8 -*-
"""Замена документа договора площадки не теряет прежний (аудит 23.09.2026, 4.M8).

До правки ручка сначала стирала старый файл, а потом проверяла новый. Новый отклонён
(415 или 413) — старого уже нет, а ссылка на него в базе осталась: документ договора
пропадал от попытки приложить не тот файл. И второй путь к той же потере: новый файл
с тем же именем ложился поверх старого, а затем «уборка старого» удаляла уже новый.
"""
import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.routers import publishers as P

LINK = 999490


class _Db:
    def __init__(self, lk):
        self.lk = lk

    def query(self, model):
        lk = self.lk
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: lk))

    def commit(self):
        pass


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(P, "log_action", lambda *a, **kw: None)
    old = P._stored_prefix("con", LINK) + "dogovor.pdf"
    (tmp_path / old).write_bytes(b"%PDF old")
    lk = SimpleNamespace(document_filename=old, document_path=str(tmp_path / old),
                         document_source="file")
    return SimpleNamespace(root=tmp_path, lk=lk, db=_Db(lk), old=old,
                           user=SimpleNamespace(id=1))


def _upload(w, name, data):
    f = UploadFile(file=io.BytesIO(data), filename=name)
    return asyncio.run(P.upload_contract_document(1, LINK, f, w.db, w.user))


def test_rejected_file_keeps_the_old_document(wired):
    with pytest.raises(HTTPException) as e:
        _upload(wired, "virus.exe", b"MZ")
    assert e.value.status_code == 415
    assert (wired.root / wired.old).read_bytes() == b"%PDF old", "старый документ стёрт"
    assert wired.lk.document_filename == wired.old


def test_same_name_replacement_leaves_the_new_file(wired):
    _upload(wired, "dogovor.pdf", b"%PDF new")
    assert (wired.root / wired.old).read_bytes() == b"%PDF new", (
        "новый файл с тем же именем удалён уборкой старого")


def test_replacement_removes_the_old_file(wired):
    _upload(wired, "dogovor-v2.pdf", b"%PDF v2")
    assert not (wired.root / wired.old).exists()
    assert (wired.root / wired.lk.document_filename).read_bytes() == b"%PDF v2"
