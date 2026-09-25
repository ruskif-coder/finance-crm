# -*- coding: utf-8 -*-
"""Кнопка «скачать» баннер в кабинете (владелец 25.09.2026).

Кабинет не читает файл сам — тома загрузок у него нет. Он проверяет, что задание своё,
и просит ядро, называя учётку и площадку ИЗ задания, а не из запроса.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import main

ACC = SimpleNamespace(id=11, name="Площадка", email="p@x.test", can_approve=False)


class _Resp:
    def __init__(self, code, body=b"PK\x03\x04", cd='attachment; filename="b.zip"'):
        self.status_code, self.content = code, body
        self.headers = {"content-disposition": cd}


@pytest.fixture
def core(monkeypatch):
    st = SimpleNamespace(calls=[], resp=_Resp(200))
    monkeypatch.setattr(main, "SERVICE_TOKEN", "t")
    monkeypatch.setattr(main, "my_task", lambda acc, tid: SimpleNamespace(
        task_id=tid, target_id=5, publisher_id=7))

    def get(url, params=None, headers=None, timeout=None):
        st.calls.append((url, params))
        return st.resp
    monkeypatch.setattr(main.httpx, "get", get)
    return st


def test_download_asks_core_for_the_file_of_the_own_task(core):
    r = main.creative_file(3, 42, ACC)
    url, params = core.calls[0]
    assert url.endswith("/api/cabinet-gw/task/3/file/42")
    assert params == {"account_id": 11, "publisher_id": 7}
    assert r.body.startswith(b"PK")
    assert "attachment" in r.headers["content-disposition"]


def test_core_refusal_is_404_without_details(core):
    core.resp = _Resp(403)
    with pytest.raises(HTTPException) as e:
        main.creative_file(3, 42, ACC)
    assert e.value.status_code == 404
