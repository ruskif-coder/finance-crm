# -*- coding: utf-8 -*-
"""Базовая ставка поверхности в «Трафики → Каталог» (владелец 16.11.2026): третье поле рядом с ID паблишера и блоком
по умолчанию. Пусто — 100; ноль, отрицательное и нечисло — отказ словами. Тест возвращает поверхность как была."""
import types

import pytest
from fastapi import HTTPException

from app.routers import traffic_catalog as tc
from app.sales.models import SalesPublisherSurface


@pytest.fixture
def surface(db, monkeypatch):
    monkeypatch.setattr(tc, "log_action", lambda *a, **k: None)
    s = db.query(SalesPublisherSurface).order_by(SalesPublisherSurface.id).first()
    if s is None:
        pytest.skip("на стенде нет поверхностей")
    keep = (s.ms_publisher_id, s.default_ms_block_id, s.base_bid)
    yield s
    db.rollback()
    s = db.get(SalesPublisherSurface, s.id)
    s.ms_publisher_id, s.default_ms_block_id, s.base_bid = keep
    db.commit()


def _edit(db, s, **kw):
    body = {"ms_publisher_id": s.ms_publisher_id, "default_ms_block_id": s.default_ms_block_id, **kw}
    return tc.edit_surface(s.id, tc.SurfaceMS(**body), db=db, user=types.SimpleNamespace(id=0, name="т"))


def test_base_bid_is_saved_and_returned(db, surface):
    out = _edit(db, surface, base_bid=161)
    assert out["base_bid"] == 161
    db.expire_all()
    assert float(db.get(SalesPublisherSurface, surface.id).base_bid) == 161


def test_empty_base_bid_means_100(db, surface):
    assert _edit(db, surface, base_bid=None)["base_bid"] == 100


@pytest.mark.parametrize("bad", [0, -5, 100001])
def test_nonsense_base_bid_is_refused(db, surface, bad):
    with pytest.raises(HTTPException) as e:
        _edit(db, surface, base_bid=bad)
    assert e.value.status_code == 400 and "ставк" in e.value.detail.lower()
