# -*- coding: utf-8 -*-
"""Вероятность сделки — одно правило для «Статусов продаж» и дашборда (владелец 23.10.2026): пустой светофор показывается
по стадии, в базу не пишется; сделка в работе (после Брони) — «факт» в базе и правке не поддаётся.
Свою сделку тест убирает вместе с журналом; уведомления и сборка РК подменены."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.routers import sales_dashboard as sd
from app.sales import probability as P


@pytest.mark.parametrize("light,stage,lost,want", [
    (None, "media_plan", False, "grey"), (None, "booking", False, "orange"), ("orange", "media_plan", False, "orange"),
    ("grey", "launch_prep", False, "green"), (None, "archive", False, "green"), ("green", "booking", True, None),
])
def test_one_rule_for_every_screen(light, stage, lost, want):
    assert P.effective(light, stage, lost) == want


@pytest.fixture
def env(monkeypatch):
    from app.ad import build
    from app.models import Role, User
    from app.notify import closing as CN
    monkeypatch.setattr(sd, "_notify_move", lambda *a, **k: None)
    monkeypatch.setattr(build, "ensure_campaign_on_move", lambda *a, **k: None)
    monkeypatch.setattr(CN, "deal_on_recon", lambda *a, **k: None)
    db = SessionLocal()
    admin = db.query(User).join(Role, Role.id == User.role_id).filter(Role.key == "admin", User.is_active == 1).first()
    adv = db.execute(text("SELECT id FROM sales_advertisers ORDER BY id LIMIT 1")).scalar()
    if not admin or not adv:
        db.close()
        pytest.skip("на стенде нет админа или рекламодателя")
    out = sd.create_deal(sd.DealCreate(advertiser_id=adv, product="тест", pipeline="Песочница", bitrix_stage="МП Подготовка",
                                       period="2026-06", amount=1000.0, title="тест вероятности в работе",
                                       probability_color="grey"), db, admin)
    try:
        yield db, admin, out["id"]
    finally:
        db.rollback()
        db.execute(text("DELETE FROM audit_log WHERE entity_type = 'sales_deal' AND entity_id = :i"), {"i": out["id"]})
        db.execute(text("DELETE FROM sales_deals WHERE id = :i"), {"i": out["id"]})
        db.commit()
        db.close()


def test_deal_entering_work_becomes_fact(env):
    from app.sales import stage_move
    from app.sales.catalog import Catalog
    from app.sales.models import SalesDeal
    db, admin, did = env
    cat = Catalog(db)
    target = next(s for s in cat.stages if s.stage_key == "launch_prep")
    stage_move.apply_move(db, db.get(SalesDeal, did), target, admin, catalog=cat, reason="тест")
    db.commit()
    assert db.execute(text("SELECT probability_color FROM sales_deals WHERE id = :i"), {"i": did}).scalar() == "green"


def test_light_of_deal_in_work_is_locked(env):
    db, admin, did = env
    db.execute(text("UPDATE sales_deals SET our_stage_id = (SELECT id FROM sales_stages WHERE stage_key = 'launch' LIMIT 1), "
                    "probability_color = 'green' WHERE id = :i"), {"i": did})
    db.commit()
    with pytest.raises(HTTPException) as e:
        sd.set_deal_probability(did, sd.ProbabilityIn(color="grey"), db, admin)
    assert e.value.status_code == 409
    assert db.execute(text("SELECT probability_color FROM sales_deals WHERE id = :i"), {"i": did}).scalar() == "green"


def test_light_before_work_still_editable(env):
    db, admin, did = env
    sd.set_deal_probability(did, sd.ProbabilityIn(color="orange"), db, admin)
    assert db.execute(text("SELECT probability_color FROM sales_deals WHERE id = :i"), {"i": did}).scalar() == "orange"
