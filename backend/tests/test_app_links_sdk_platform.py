# -*- coding: utf-8 -*-
"""Режим ссылок «диплинк SDK» и платформа блока приложения (владелец 02.10.2026)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.main  # noqa: F401
from app.launch_prep import pub_rules as R


def test_sdk_mode_is_known_and_hinted():
    assert "sdk" in R.APP_LINKS
    h = R.landing_hint({"app_links": "sdk"})
    assert "deeplink+://" in h and "primaryUrl" in h
    assert "https://" in R.landing_hint({"app_links": "web"})
    assert R.landing_hint(None) is None


def test_sdk_mode_puts_landing_into_href():
    dl = "deeplink+://navigate?primaryUrl=aHR0cHM6Ly9hLnJ1Lw==&primaryTrackingUrl={LINK_ESC}"
    assert R.click_href({"app_links": "sdk"}, dl, None) == dl


def test_no_hard_check_by_mode():
    """Без жёсткой проверки: режим подсказывает, но https на sdk-площадке принимается."""
    assert R.validate_landing("https://a.ru/x", "app") == "https://a.ru/x"


def test_db_accepts_sdk_and_block_platform():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SAVEPOINT t"))
        sid = db.execute(text("SELECT id FROM sales_publisher_surfaces WHERE kind='app' LIMIT 1")).scalar()
        if not sid:
            pytest.skip("нет app-поверхности")
        db.execute(text("UPDATE sales_publisher_surfaces SET app_links='sdk' WHERE id=:i"), {"i": sid})
        bid = db.execute(text("SELECT id FROM publisher_block WHERE surface='app' LIMIT 1")).scalar()
        if bid:
            db.execute(text("UPDATE publisher_block SET platform='ios' WHERE id=:i"), {"i": bid})
    finally:
        db.rollback()
        db.close()


def test_block_out_carries_platform():
    from app.routers import traffic_catalog as tc
    b = SimpleNamespace(id=1, ms_block_id="1", name="n", page_type=None, network=None,
                        is_active=True, platform="android")
    assert tc._block_out(b)["platform"] == "android"


def test_platform_only_for_app_block():
    from app.routers import traffic_catalog as tc
    with pytest.raises(Exception):
        tc._platform_for("web", "ios")
    assert tc._platform_for("app", "ios") == "ios"
    assert tc._platform_for("app", "") is None
