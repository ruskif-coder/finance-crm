# -*- coding: utf-8 -*-
"""Правка медиаплана сразу тянет за собой систему (владелец 18.11.2026; разбор «что не обновляется сразу»).

Поломки, которые ловит набор:
- сохранение МП снова теряет факт, введённый аккаунтом в итоговой сверке (строки пересоздаются с новыми id);
- услуга текстом у сделки (`product` — по нему реестр показывает услугу, цвет и метку WEB/APP) снова отстаёт от МП;
- период получателей сборки не едет за периодом сделки, или едет и у суженного руками;
- пересчёт РК снова только при смене объёма/бюджета/дат (смена поверхности или услуги ждала ночи);
- путь записи МП в обход сохранения (правка из реестра, привязка, удаление, сдвиг месяца) не пересчитывает РК."""
import inspect
from datetime import date
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.ad import volumes_now
from app.database import SessionLocal
from app.final_recon.models import FinalReconFactEntry
from app.launch_prep.models import LaunchPrepTarget
from app.routers import media_plans as MP
from app.routers import sales_status
from app.sales import mp_follow
from app.sales.models import SalesDeal, SalesMediaPlan, SalesMediaPlanRow, SalesPublisher, SalesService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _plan_with_rows(db):
    p = (db.query(SalesMediaPlan).join(SalesMediaPlanRow, SalesMediaPlanRow.plan_id == SalesMediaPlan.id)
         .filter(SalesMediaPlan.deal_id.isnot(None)).order_by(SalesMediaPlan.id.desc()).first())
    assert p is not None, "на стенде нет медиаплана со строками и сделкой"
    return p


def _as_input(rows):
    return SimpleNamespace(extras=[], rows=[SimpleNamespace(position=r.position, format=r.format, model=r.model, inventory=r.inventory,
                                                          volume=r.volume, unit_price=r.unit_price, discount=r.discount,
                                                          forecast=r.forecast) for r in rows])


def test_rewriting_rows_keeps_entered_fact(db):
    p = _plan_with_rows(db)
    rows = db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == p.id).order_by(SalesMediaPlanRow.sort_order).all()
    db.query(FinalReconFactEntry).filter(FinalReconFactEntry.deal_id == p.deal_id).delete(synchronize_session=False)
    e = FinalReconFactEntry(deal_id=p.deal_id, mp_row_id=rows[0].id, fact_volume=123)
    db.add(e)
    db.flush()
    old = mp_follow.snapshot_rows(db, p.id)
    MP._write_children(db, p.id, _as_input(rows))          # то же, что делает сохранение МП: строки заново, новые id
    assert mp_follow.carry_fact_entries(db, p.deal_id, old, p.id) == 1
    db.flush()
    new_first = db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == p.id).order_by(SalesMediaPlanRow.sort_order).first()
    assert e.mp_row_id == new_first.id != rows[0].id


def test_save_carries_fact_in_both_write_paths():
    src = inspect.getsource(MP.save_media_plan)
    assert src.count("carry_fact_entries(") == 2 and src.count("snapshot_rows(") == 2


def test_deal_product_follows_plan_service(db):
    p = _plan_with_rows(db)
    first = db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == p.id).order_by(SalesMediaPlanRow.sort_order).first()
    svc = db.query(SalesService).filter(SalesService.name == (first.position or "").strip()).first()
    if svc is None:
        svc = db.query(SalesService).order_by(SalesService.id).first()
        first.position = svc.name
    deal = db.get(SalesDeal, p.deal_id)
    deal.product = "СТАРАЯ УСЛУГА"
    db.flush()
    MP._sync_deal_from_plan(db, p, None)
    assert deal.product == svc.name


def test_target_period_follows_deal_but_narrowed_stays(db):
    deal = db.query(SalesDeal).filter(SalesDeal.period_from.isnot(None)).order_by(SalesDeal.id).first()
    pubs = db.query(SalesPublisher).order_by(SalesPublisher.id).limit(2).all()
    svc = db.query(SalesService).order_by(SalesService.id).first()
    db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == deal.id,
                                      LaunchPrepTarget.publisher_id.in_([p.id for p in pubs])).delete(synchronize_session=False)
    old_from, old_to = date(2026, 11, 1), date(2026, 11, 30)
    same = LaunchPrepTarget(deal_id=deal.id, publisher_id=pubs[0].id, service_id=svc.id, surface_kind="web",
                            period_from=old_from, period_to=old_to)
    narrow = LaunchPrepTarget(deal_id=deal.id, publisher_id=pubs[1].id, service_id=svc.id, surface_kind="web",
                              period_from=date(2026, 11, 18), period_to=old_to)
    db.add_all([same, narrow])
    db.flush()
    n = mp_follow.follow_period(db, deal.id, old_from, old_to, date(2026, 12, 1), date(2026, 12, 31))
    assert n == 1
    assert (same.period_from, same.period_to) == (date(2026, 12, 1), date(2026, 12, 31))
    assert narrow.period_from == date(2026, 11, 18)


def test_replan_refreshes_placements_even_when_plan_numbers_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr(volumes_now.build, "replan_deal", lambda db, deal_id: {"campaign_id": 1, "changed": False})
    monkeypatch.setattr(volumes_now, "refresh_volumes_now", lambda db, deal_id: calls.append(deal_id) or {"ok": True})
    volumes_now.replan_now(None, 42)
    assert calls == [42], "смена поверхности/услуги без смены объёма тоже пересобирает РК и лимиты"


def test_replan_skipped_when_deal_has_no_campaign(monkeypatch):
    calls = []
    monkeypatch.setattr(volumes_now.build, "replan_deal", lambda db, deal_id: None)
    monkeypatch.setattr(volumes_now, "refresh_volumes_now", lambda db, deal_id: calls.append(deal_id))
    assert volumes_now.replan_now(None, 42) is None and calls == []


@pytest.mark.parametrize("fn", [MP.patch_media_plan, MP.link_deal, MP.delete_media_plan, sales_status.apply_moves])
def test_every_write_path_replans_the_campaign(fn):
    assert "follow_plan_change(" in inspect.getsource(fn), f"{fn.__name__} меняет МП/период и не пересчитывает РК"


def test_status_shift_moves_target_periods():
    assert "follow_period(" in inspect.getsource(sales_status.apply_moves)
