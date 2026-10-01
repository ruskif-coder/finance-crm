# -*- coding: utf-8 -*-
"""Вкладка «Логи» (владелец 01.10.2026): строка = сделка + площадка + креатив."""
from types import SimpleNamespace as NS

from app.database import SessionLocal
from app.traffic import logs


class _Eng:
    def __init__(self, rows):
        self.rows = rows

    def connect(self):
        eng = self

        class _C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a, **k):
                return NS(mappings=lambda: NS(all=lambda: eng.rows))
        return _C()


def _row(**k):
    base = {"id": 1, "ts": None, "method": "Creative.add", "entity_type": "creative", "local_ref": None,
            "ms_xxhash": None, "ok": True, "error": None, "contour": "prod", "request": None, "response": None}
    return {**base, **k}


def test_dsp_row_resolves_creative_by_cr_ref():
    from sqlalchemy import text
    db = SessionLocal()
    try:
        cr = db.execute(text("SELECT c.id FROM ad_campaign_creative c WHERE c.placement_id IS NOT NULL LIMIT 1")).scalar()
        if not cr:
            import pytest
            pytest.skip("нет креативов РК")
        out = logs.dsp_rows(db, engine=_Eng([_row(local_ref=f"cr{cr}")]))
        assert out[0]["deal"] and out[0]["publisher"] and out[0]["creative"]
    finally:
        db.close()


def test_dsp_row_without_link_stays_empty_not_failing():
    db = SessionLocal()
    try:
        out = logs.dsp_rows(db, engine=_Eng([_row(local_ref="probe-3009", entity_type="campaign")]))
        assert out[0]["deal"] is None and out[0]["method"] == "Creative.add"
    finally:
        db.close()


def test_wr_rows_have_deal():
    db = SessionLocal()
    try:
        rows = logs.wr_rows(db, limit=20)
        assert all(r["deal"] for r in rows if r["entity"] in ("insertion", "tag", "project"))
    finally:
        db.close()


def test_wake_targeting_never_fails_launch(monkeypatch):
    from app.dsp import targeting_creative as tc
    from app.routers import traffic_dashboard as td
    monkeypatch.setattr(tc, "blind_sets", lambda db, ids: set())

    def boom(db, s):
        raise tc.TargetingCreativeError("кабинет не задан")
    monkeypatch.setattr(tc, "ensure_live", boom)
    db = SessionLocal()
    try:
        from sqlalchemy import text
        deal = db.execute(text("SELECT deal_id FROM launch_prep_creative_set WHERE erid IS NOT NULL LIMIT 1")).scalar()
        if not deal:
            import pytest
            pytest.skip("нет комплектов с ЕРИД")
        r = td.wake_targeting(db, deal)
        assert r["woken"] == 0 and r["errors"] and "кабинет не задан" in r["errors"][0]
    finally:
        db.close()


def test_dsp_rows_all_when_no_limit():
    """Ограничение ленты 500 / 1000 / все (владелец 01.10.2026): None — без предела."""
    db = SessionLocal()
    try:
        rows = [_row(id=i, local_ref=f"probe-{i}") for i in range(1200, 0, -1)]
        assert len(logs.dsp_rows(db, limit=500, engine=_Eng(rows))) == 500
        assert len(logs.dsp_rows(db, limit=None, engine=_Eng(rows))) == 1200
    finally:
        db.close()


def test_download_keeps_full_bodies():
    """Скачанный лог — архив, а не экран: тело запроса не обрезается."""
    db = SessionLocal()
    try:
        big = "x" * (logs.MAX_BODY + 500)
        out = logs.dsp_rows(db, engine=_Eng([_row(local_ref="probe-1", request=big)]), full=True)
        assert out[0]["request"] == big
        text_ = logs.as_text("dsp", out)
        assert big in text_ and "Creative.add" in text_
    finally:
        db.close()


def test_download_endpoint_gives_text_file():
    from app.routers import traffic_balancer as TB
    db = SessionLocal()
    try:
        r = TB.exchange_logs_download(system="weborama", limit=5, only_errors=False,
                                      deal="ab/../c", prod_only=True, db=db, user=None)
        cd = r.headers["content-disposition"]
        assert cd.startswith("attachment;") and "log_weborama_ABC_" in cd and ".txt" in cd
        assert r.body.decode("utf-8").startswith("Лог обмена с Weborama")
    finally:
        db.close()
