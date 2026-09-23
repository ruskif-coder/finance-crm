# -*- coding: utf-8 -*-
"""Прибор: медиаплан не пишет в чужую сделку (аудит 23.09.2026, 1.M1 / 3.M6).

Область видимости сделок проверялась только в файловых ручках брифа. `link_deal`
переписывал чужой сделке название, сумму и стадию, новый план с `deal_id` не проверял
даже существование сделки, а бриф чужой сделки читался и уходил в Битрикс.

Роль «только свои» здесь подставляется подменой области видимости: так проверяется
сама ручка, а не настройка ролей на стенде.
"""
import pytest
from fastapi import HTTPException

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import media_plans as mp
from app.routers import sales_dashboard as sd
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesMediaPlan


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def stranger(db, monkeypatch):
    """Пользователь с областью «свои», которому не принадлежит ни одна сделка."""
    monkeypatch.setattr(mp, "_guard_owned", lambda *a, **k: None)
    monkeypatch.setattr(sd, "_own_rep_ids_or_all", lambda *a, **k: {-1})
    return db.query(User).filter(User.is_active == 1).first()


@pytest.fixture
def open_deal(db):
    """Сделка на первой стадии — фиксация плана её не касается, мешать может только область."""
    first = Catalog(db).first()
    deal = db.query(SalesDeal).first()
    deal.our_stage_id = first.id
    db.flush()
    return deal


@pytest.fixture
def plan(db):
    return db.query(SalesMediaPlan).order_by(SalesMediaPlan.id.desc()).first()


def test_link_to_a_deal_outside_the_scope_is_refused(db, stranger, open_deal, plan):
    with pytest.raises(HTTPException) as e:
        mp.link_deal(plan.id, mp.LinkDealIn(deal_id=open_deal.id), db=db, current_user=stranger)
    assert e.value.status_code == 403


def test_brief_of_a_foreign_deal_is_not_read_or_written(db, stranger, open_deal, plan):
    plan.deal_id = open_deal.id
    db.flush()
    with pytest.raises(HTTPException) as e:
        mp.mp_get_deal_brief(plan.id, refresh=0, db=db, current_user=stranger)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        mp.mp_save_deal_brief(plan.id, mp.DealBriefIn(brief="чужое"), db=db, current_user=stranger)
    assert e.value.status_code == 403


def test_new_plan_for_a_missing_deal_is_refused(db, stranger):
    data = mp.MpIn(group_id=None, deal_id=999_999_999, rows=[], extras=[], title="прибор")
    with pytest.raises(HTTPException) as e:
        mp.save_media_plan(data, db=db, current_user=stranger)
    assert e.value.status_code == 404


def test_new_plan_for_a_foreign_deal_is_refused(db, stranger, open_deal):
    data = mp.MpIn(group_id=None, deal_id=open_deal.id, rows=[], extras=[], title="прибор")
    with pytest.raises(HTTPException) as e:
        mp.save_media_plan(data, db=db, current_user=stranger)
    assert e.value.status_code == 403


def test_unlinking_from_a_foreign_deal_is_refused(db, stranger, open_deal, plan):
    """Отвязка тоже меняет сделку — оставляет её без плана. До ревью 23.09.2026 область
    проверялась только у сделки, К которой привязывают."""
    plan.deal_id = open_deal.id
    db.flush()
    with pytest.raises(HTTPException) as e:
        mp.link_deal(plan.id, mp.LinkDealIn(deal_id=None), db=db, current_user=stranger)
    assert e.value.status_code == 403
