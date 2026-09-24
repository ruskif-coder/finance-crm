# -*- coding: utf-8 -*-
"""Шлюз ядра сам проверяет «только просмотр» (аудит 23.09.2026, 1.L3; владелец 24.09).

Кабинет проверяет роль у себя, но шлюз этого не повторял — даже для вердикта. Проверка,
оставленная на вызывающей стороне, — это отсутствие проверки: так написано в шапке
соседней ручки, и здесь действует то же правило.
"""
import io
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.models  # noqa: F401
from app.cabinet import scope
from app.routers import cabinet_gateway as gw

SRC = Path(gw.__file__)


class _Db:
    def __init__(self, acc):
        self.acc = acc

    def query(self, model):
        acc = self.acc
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: acc))


def test_a_viewer_is_refused_where_approval_is_needed(monkeypatch):
    monkeypatch.setattr(scope, "account_sees_publisher", lambda db, acc, pid: True)
    viewer = SimpleNamespace(id=1, can_approve=False, cabinet_id=2, name="В")
    with pytest.raises(HTTPException) as e:
        gw._actor(_Db(viewer), 1, 7, approve=True)
    assert e.value.status_code == 403
    assert gw._actor(_Db(viewer), 1, 7) is viewer, "чтение и заявки просмотру доступны"


def test_every_changing_door_asks_for_approval():
    """Вердикт, посадочная, медиакит, файл доработки — все четыре двери с правом ответа."""
    src = io.open(SRC, encoding="utf-8").read()
    for fn in ("cabinet_verdict", "cabinet_target_url", "cabinet_media_kit",
               "cabinet_rework_file"):
        body = src[src.index(f"def {fn}("):]
        body = body[:body.index("\n@router")] if "\n@router" in body else body
        assert re.search(r"_actor\([^)]*approve=True", body), (
            f"{fn}: действие площадки не проверяет право ответа")
