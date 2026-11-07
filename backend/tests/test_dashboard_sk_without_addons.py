# -*- coding: utf-8 -*-
"""Дашборд продаж: «наша сумма» и бонусы — СК без доп. услуг (владелец 07.11.2026: «да, должно корректно учитываться»).
Как в сверке и ДС: СК вычитается только из базовой услуги, допы остаются нашими целиком.

Руками: сделка 120 000 (база 100 000 + допы 20 000), СК 30 % → наша сумма 120 000 − 30 000 = 90 000 (не 84 000)."""
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.sales import mp_amounts as MA


def test_our_sum_keeps_addons_whole():
    assert MA.our_net(120000.0, 30.0, 20000.0) == 90000.0


def test_our_sum_without_addons_is_as_before():
    assert MA.our_net(100000.0, 30.0, 0.0) == 70000.0


def test_addons_never_make_the_sk_negative():
    assert MA.our_net(10000.0, 30.0, 25000.0) == 10000.0


def test_extras_are_taken_from_the_same_latest_plans():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT p.deal_id FROM sales_media_plans p JOIN sales_media_plan_extras e ON e.plan_id = p.id
             WHERE p.deal_id IS NOT NULL AND e.total > 0
               AND p.version = (SELECT max(version) FROM sales_media_plans x WHERE x.group_id = p.group_id)
               AND EXISTS (SELECT 1 FROM sales_media_plan_rows r WHERE r.plan_id = p.id)
             ORDER BY p.deal_id LIMIT 1""")).first()
        if not row:
            import pytest
            pytest.skip("на стенде нет сделки с платным допом")
        want = db.execute(text("""
            SELECT coalesce(sum(e.total), 0) FROM sales_media_plans p JOIN sales_media_plan_extras e ON e.plan_id = p.id
             WHERE p.deal_id = :d AND p.version = (SELECT max(version) FROM sales_media_plans x WHERE x.group_id = p.group_id)
               AND EXISTS (SELECT 1 FROM sales_media_plan_rows r WHERE r.plan_id = p.id)"""), {"d": row[0]}).scalar()
        assert MA.extras_net_by_deal(db, [row[0]])[row[0]] == round(float(want), 2)
    finally:
        db.rollback()
        db.close()
