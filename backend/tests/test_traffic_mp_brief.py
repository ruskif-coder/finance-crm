# -*- coding: utf-8 -*-
"""Бриф медиаплана для трафика — вторая вкладка «Задач РК» (владелец 29.09.2026):
только гео и таргетинг, остальная шапка трафику не отдаётся."""
from sqlalchemy import text

from app.ad.build import TG_GROUPS, deal_mp_brief
from app.database import SessionLocal


def test_brief_has_only_geo_and_targeting_groups_in_order():
    db = SessionLocal()
    try:
        did = db.execute(text("SELECT deal_id FROM sales_media_plans WHERE deal_id IS NOT NULL "
                              "ORDER BY id DESC LIMIT 1")).scalar()
        b = deal_mp_brief(db, did)
        assert b is not None and set(b) == {"geo", "targeting"}, "трафику лишнего не отдаём"
        assert [g["key"] for g in b["targeting"]] == [k for k, _ in TG_GROUPS]
        assert all(isinstance(g["values"], list) for g in b["targeting"])
        assert deal_mp_brief(db, -1) is None
    finally:
        db.close()
