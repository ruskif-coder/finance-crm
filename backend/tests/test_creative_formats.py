# -*- coding: utf-8 -*-
"""Формат креатива поверхности площадки (владелец 13.10.2026).

У каждой пары «площадка × веб/апп» — свой стандартный тип креатива DSP, выбранный из справочника
`ad_creative_formats` (HTML, TEASER, VIDEO_INLINE, VIDEO_VAST — типология DSP). По умолчанию у всех
HTML (так конвейер и работает), у Купера — TEASER. Пока выбор только записывается: отправку тизера
конвейер не умеет, и это сознательно не включено.
"""
import pathlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.database import SessionLocal
from app.routers import traffic_pub_rules as R
from app.sales.models import SalesPublisher, SalesPublisherSurface

MIG = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "2026-10-13_creative_formats.sql"
_ADMIN = SimpleNamespace(role=SimpleNamespace(key="admin"), id=None, name="тест")


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _surface(db):
    return (db.query(SalesPublisherSurface).join(SalesPublisher, SalesPublisher.id == SalesPublisherSurface.publisher_id)
            .filter(SalesPublisher.status != "АРХИВ", SalesPublisherSurface.kind == "web").order_by(SalesPublisherSurface.id).first())


def test_directory_holds_the_four_dsp_types(db):
    keys = {k for (k,) in db.execute(text("SELECT key FROM ad_creative_formats WHERE is_active"))}
    assert keys == {"HTML", "TEASER", "VIDEO_INLINE", "VIDEO_VAST"}


def test_every_surface_has_a_format_and_default_is_html(db):
    bad = db.execute(text("SELECT count(*) FROM sales_publisher_surfaces WHERE creative_format IS NULL")).scalar()
    assert bad == 0
    non_html = db.execute(text("""SELECT lower(p.name), s.kind FROM sales_publisher_surfaces s
        JOIN sales_publishers p ON p.id = s.publisher_id WHERE s.creative_format <> 'HTML'""")).all()
    assert all("kuper" in n or "купер" in n for n, _ in non_html), non_html


def test_kuper_app_is_teaser(db):
    rows = db.execute(text("""SELECT s.creative_format FROM sales_publisher_surfaces s
        JOIN sales_publishers p ON p.id = s.publisher_id
        WHERE s.kind = 'app' AND (lower(p.name) LIKE '%kuper%' OR lower(p.name) LIKE '%купер%')""")).all()
    assert rows and all(r[0] == "TEASER" for r in rows)


def test_list_offers_directory_and_value(db):
    out = R.list_rules(db=db, current_user=_ADMIN)
    assert {f["key"] for f in out["formats"]} == {"HTML", "TEASER", "VIDEO_INLINE", "VIDEO_VAST"}
    assert all("creative_format" in i for i in out["items"])


def test_update_rejects_value_outside_directory(db):
    s = _surface(db)
    with pytest.raises(HTTPException) as e:
        R.update_rule(s.id, R.RuleIn(creative_format="GIF"), db, _ADMIN)
    assert e.value.status_code == 400


def test_update_without_format_keeps_it(db):
    s = _surface(db)
    before = s.creative_format
    R.update_rule(s.id, R.RuleIn(placement_channel=s.placement_channel, app_links=s.app_links,
                                 adfox_extra_code=s.adfox_extra_code), db, _ADMIN)
    db.refresh(s)
    assert s.creative_format == before
    db.rollback()


def test_migration_seeds_kuper_only_when_column_is_new():
    sql = MIG.read_text(encoding="utf-8")
    assert "information_schema.columns" in sql, "бэкфилл Купера — только при первом накате (иначе повтор затрёт ручную правку)"
    assert "DROP" not in sql.upper()
