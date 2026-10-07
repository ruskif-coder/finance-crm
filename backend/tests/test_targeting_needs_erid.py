# -*- coding: utf-8 -*-
"""Ссылка нацеливания: первичной проверке ЕРИД не нужен, боевой РК — нужен (владелец 07.10.2026).

Два разных случая на одной ручке:
  · ПЕРВИЧНАЯ ПРОВЕРКА баннера (очередь согласования у трафика, `first_check=true`) идёт ДО выдачи
    маркера: копия нацеливания у демоклиента заводится с общей заглушкой `TEST_ERID`, пиксель
    Weborama на ней не нужен. Ссылка выпускается без ЕРИД;
  · НАЦЕЛИВАНИЕ В БОЕВОЙ РК (дашборд трафика, сводка креативов сделки) снимает скриншоты размещения,
    и копия с заглушкой там ни к чему: нужен боевой ЕРИД (`ord.readiness`). Без него отказ 409
    «ждём ЕРИД», в DSP не ходим (9HT4V9 №3: ссылка 05.10 до ЕРИД, копия застряла на TEST00000).

06.10 (v2.6.74.1) отказ стоял для ВСЕХ вызовов и закрыл первичную проверку; 07.10 первый случай
выведен из-под него. Умолчание строгое: забытый параметр не выпустит боевую ссылку с заглушкой.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dsp import targeting_creative as tc
from app.routers import launch_prep as lp


def _db_with(row):
    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return row

    class _Db:
        def query(self, *a, **k):
            return _Q()

    return _Db()


def _issue(monkeypatch, row, **kw):
    called = []
    monkeypatch.setattr(tc, "ensure_live", lambda db, r: called.append(r.no) or {
        "xxhash": "LIVE000000000001", "creative_status": "LAUNCHED",
        "campaign_status": "LAUNCHED", "active": True, "reason": None})
    monkeypatch.setattr("app.dsp.targeting_link.issue",
                        lambda crid: SimpleNamespace(url=f"https://dsp.example/t/{crid}", expires_at=None))
    monkeypatch.setattr(lp, "_deal", lambda db, deal_id, user: SimpleNamespace(id=1, code="T"))
    monkeypatch.setattr(lp, "log_action", lambda *a, **k: None)
    try:
        out = lp.issue_targeting_link(1, _db_with(row), SimpleNamespace(id=1), **kw)
    except HTTPException as e:
        return e, called
    return out, called


NO_ERID = dict(id=1, deal_id=1, no=3, erid=None, ord_status=None, erid_source=None)
NOT_READY = dict(id=1, deal_id=1, no=4, erid="2SDtest", ord_status="Rejected", erid_source=None)
READY = dict(id=1, deal_id=1, no=5, erid="2SDtest", ord_status="Active", erid_source=None)


@pytest.mark.parametrize("fields", [NO_ERID, NOT_READY])
def test_first_check_needs_no_erid(monkeypatch, fields):
    out, called = _issue(monkeypatch, SimpleNamespace(**fields), first_check=True)
    assert called == [fields["no"]], "копию нацеливания надо завести и запустить и без ЕРИД"
    assert out["url"].endswith("LIVE000000000001") and out["active"] is True


@pytest.mark.parametrize("fields", [NO_ERID, NOT_READY])
def test_live_campaign_targeting_waits_for_a_ready_erid(monkeypatch, fields):
    err, called = _issue(monkeypatch, SimpleNamespace(**fields))      # умолчание — боевой режим
    assert isinstance(err, HTTPException) and err.status_code == 409
    assert "ЕРИД" in err.detail and "позже" in err.detail
    assert not called, "без боевого ЕРИД в DSP не ходим"


def test_live_campaign_targeting_works_with_a_ready_erid(monkeypatch):
    out, called = _issue(monkeypatch, SimpleNamespace(**READY))
    assert called == [5] and out["url"]


def test_the_copy_carries_the_placeholder_until_the_marker_is_ready():
    """Заглушка — только пока маркер не готов; готовый подставляется (боевое правило не ослаблено)."""
    assert tc.erid_of(SimpleNamespace(**NO_ERID)) == tc.TEST_ERID
    assert tc.erid_of(SimpleNamespace(**NOT_READY)) == tc.TEST_ERID
    assert tc.erid_of(SimpleNamespace(**READY)) == "2SDtest"
