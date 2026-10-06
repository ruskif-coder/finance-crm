# -*- coding: utf-8 -*-
"""Ссылку нацеливания выпускаем только при готовом ЕРИД (владелец 06.10.2026).

9HT4V9: ссылка по комплекту №3 выпущена 05.10 до ЕРИД — копия нацеливания ушла с
заглушкой TEST00000, а настоящий ЕРИД, выданный на следующий день, до неё не дошёл.
Теперь без готового ЕРИД — отказ «ждём ЕРИД, загляните позже», в DSP не ходим."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import launch_prep as lp


def test_no_erid_no_targeting_link(monkeypatch):
    from app.dsp import targeting_creative as tc
    called = []
    monkeypatch.setattr(tc, "ensure_live", lambda *a, **k: called.append(1) or {"xxhash": "X"})
    row = SimpleNamespace(id=1, deal_id=1, no=3, erid=None, ord_status=None)

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return row

    class _Db:
        def query(self, *a, **k):
            return _Q()

    monkeypatch.setattr(lp, "_deal", lambda db, deal_id, user: SimpleNamespace(id=1, code="T"))
    with pytest.raises(HTTPException) as e:
        lp.issue_targeting_link(1, _Db(), SimpleNamespace(id=1))
    assert e.value.status_code == 409 and "ЕРИД" in e.value.detail and "позже" in e.value.detail
    assert not called, "без ЕРИД в DSP не ходим"


def test_erid_issued_but_not_ready_also_waits(monkeypatch):
    """Маркер выдан, но в ОРД не готов (не Active/Registering/…) — тоже ждём."""
    from app.ord import readiness
    s = SimpleNamespace(erid="2SDtest", ord_status="Rejected")
    assert readiness.ready_erid(s) is None
