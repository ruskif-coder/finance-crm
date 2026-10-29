# -*- coding: utf-8 -*-
"""Разаллокация в кабинете (владелец 29.10.2026): файл собирает ядро; кабинет проверяет, что сверка своя и согласована,
и зовёт ядро с площадкой ИЗ сверки, а не из запроса."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import recon as R

ACC = SimpleNamespace(id=11, name="Площадка", email="p@x.test", can_approve=False)


class _Resp:
    def __init__(self, code, body=b"PK\x03\x04"):
        self.status_code, self.content = code, body
        self.headers = {"content-disposition": 'attachment; filename="razaloc_2026-10.xlsx"'}


@pytest.fixture
def core(monkeypatch):
    st = SimpleNamespace(calls=[], resp=_Resp(200), verdict="согласовано")
    monkeypatch.setattr(R, "SERVICE_TOKEN", "t")
    monkeypatch.setattr(R, "_core_or_503", lambda: None)
    monkeypatch.setattr(R, "_mine", lambda acc, rid: SimpleNamespace(request_id=rid, publisher_id=7, verdict=st.verdict))

    def get(url, params=None, headers=None, timeout=None):
        st.calls.append((url, params))
        return st.resp
    monkeypatch.setattr(R.httpx, "get", get)
    return st


def test_several_agreed_recons_are_one_core_call(core):
    """Кнопка месяца (владелец 29.10.2026): все площадки месяца — одним файлом, вкладки собирает ядро."""
    r = R.razaloc([5, 6], ACC)
    (url, params), = core.calls
    assert url.endswith("/api/cabinet-gw/recon/razaloc.xlsx")
    assert params == {"account_id": 11, "ids": [5, 6]}
    assert r.body.startswith(b"PK")


def test_one_not_agreed_recon_blocks_the_file_and_core_is_not_called(core):
    core.verdict = None
    with pytest.raises(HTTPException) as e:
        R.razaloc([5], ACC)
    assert e.value.status_code == 409 and core.calls == []


def test_empty_or_huge_list_is_400(core):
    for ids in ([], list(range(1, 102))):
        with pytest.raises(HTTPException) as e:
            R.razaloc(ids, ACC)
        assert e.value.status_code == 400
    assert core.calls == []


def test_core_refusal_does_not_leak_details(core):
    core.resp = _Resp(500)
    with pytest.raises(HTTPException) as e:
        R.razaloc([5], ACC)
    assert e.value.status_code == 502
