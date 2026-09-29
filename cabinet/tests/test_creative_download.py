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
    monkeypatch.setattr(main, "my_task", lambda acc, tid, agreed=False: SimpleNamespace(
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


def test_revoke_goes_to_core_with_own_task_and_approver(monkeypatch):
    """«Отозвать» в актуальных кампаниях: задание своё, право согласовывать, причина — к ядру
    (владелец 29.09.2026). Проверка границы по времени — в ядре, не здесь."""
    from types import SimpleNamespace as NS
    import pytest
    from fastapi import HTTPException
    calls = []
    monkeypatch.setattr(main, "require_approver", lambda acc: None)
    monkeypatch.setattr(main, "my_task", lambda acc, tid, agreed=False: NS(
        task_id=tid, publisher_id=7, target_id=1) if agreed else None)
    monkeypatch.setattr(main, "call_core", lambda m, p, b: calls.append((m, p, b)) or {"verdict": "на доработку"})
    acc = NS(id=3, name="Иванов", email="i@x.ru")
    out = main.revoke_agreement(55, main.RevokeIn(reason="поменять текст"), acc=acc)
    assert out == {"verdict": "на доработку"}
    assert calls[0][1] == "/api/cabinet-gw/pair/55/revoke" and calls[0][2]["publisher_id"] == 7
    with pytest.raises(HTTPException):
        main.revoke_agreement(55, main.RevokeIn(reason="  "), acc=acc)
