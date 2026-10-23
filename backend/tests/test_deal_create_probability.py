# -*- coding: utf-8 -*-
"""Новая сделка сразу со светофором (владелец 23.10.2026, «Статусы продаж»): клик по ячейке «месяц × вероятность»
открывает стандартную форму, и вероятность ячейки уходит в сделку тем же запросом, а не вторым вызовом.
Сделку и строку журнала тест убирает за собой."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.routers import sales_dashboard as sd


@pytest.fixture
def ctx():
    from app.models import Role, User
    db = SessionLocal()
    admin = db.query(User).join(Role, Role.id == User.role_id).filter(Role.key == "admin", User.is_active == 1).first()
    adv = db.execute(text("SELECT id FROM sales_advertisers ORDER BY id LIMIT 1")).scalar()
    if not admin or not adv:
        db.close()
        pytest.skip("на стенде нет админа или рекламодателя")
    made = []
    try:
        yield db, admin, adv, made
    finally:
        db.rollback()
        for i in made:
            db.execute(text("DELETE FROM audit_log WHERE entity_type = 'sales_deal' AND entity_id = :i"), {"i": i})
            db.execute(text("DELETE FROM sales_deals WHERE id = :i"), {"i": i})
        db.commit()
        db.close()


def _payload(adv, **kw):
    return sd.DealCreate(advertiser_id=adv, product="тест", pipeline="Песочница", bitrix_stage="МП Подготовка",
                         period="2026-11", amount=1000.0, title="тест светофора при создании", **kw)


@pytest.mark.parametrize("color", ["grey", "orange", "green"])
def test_deal_is_born_with_the_cell_probability(ctx, color):
    db, admin, adv, made = ctx
    out = sd.create_deal(_payload(adv, probability_color=color), db, admin)
    made.append(out["id"])
    assert db.execute(text("SELECT probability_color FROM sales_deals WHERE id = :i"), {"i": out["id"]}).scalar() == color


def test_without_probability_the_deal_stays_unmarked(ctx):
    db, admin, adv, made = ctx
    out = sd.create_deal(_payload(adv), db, admin)
    made.append(out["id"])
    assert db.execute(text("SELECT probability_color FROM sales_deals WHERE id = :i"), {"i": out["id"]}).scalar() is None


def test_unknown_colour_is_refused_before_anything_is_written(ctx):
    db, admin, adv, made = ctx
    before = db.execute(text("SELECT count(*) FROM sales_deals")).scalar()
    with pytest.raises(HTTPException) as e:
        sd.create_deal(_payload(adv, probability_color="red"), db, admin)
    assert e.value.status_code == 400
    assert db.execute(text("SELECT count(*) FROM sales_deals")).scalar() == before
