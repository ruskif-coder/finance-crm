# -*- coding: utf-8 -*-
"""Учётка «только просмотр» не меняет ничего на стороне площадки (владелец 24.09.2026).

До этого запрет стоял только на вердикте: посадочную ссылку, медиакит и файл к
доработке «только просмотр» менял наравне с ответственным (аудит 23.09.2026, 1.L3).
Владелец: «нет» — просмотр значит просмотр. Отказ — ДО обращения к ядру и до чтения
файла: смотреть тут нечего, а тратить на него память кабинета незачем.
"""
import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import main

VIEWER = SimpleNamespace(id=1, name="Смотрящий", email="v@x.test", can_approve=False)


@pytest.fixture(autouse=True)
def no_core(monkeypatch):
    monkeypatch.setattr(main, "call_core",
                        lambda *a, **kw: pytest.fail("запрос ушёл в ядро"))
    monkeypatch.setattr(main, "my_task", lambda acc, tid: SimpleNamespace(
        task_id=tid, target_id=5, publisher_id=7))
    monkeypatch.setattr(main, "account_publishers",
                        lambda aid: [SimpleNamespace(publisher_id=7)])


def _file():
    return UploadFile(file=io.BytesIO(b"%PDF"), filename="kit.pdf")


def test_viewer_cannot_set_the_landing():
    with pytest.raises(HTTPException) as e:
        main.set_url(3, main.UrlIn(url="https://site.test/"), VIEWER)
    assert e.value.status_code == 403


def test_viewer_cannot_upload_a_media_kit():
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.media_kit(_file(), VIEWER))
    assert e.value.status_code == 403


def test_viewer_cannot_attach_a_rework_file():
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.rework_file(3, _file(), VIEWER))
    assert e.value.status_code == 403
