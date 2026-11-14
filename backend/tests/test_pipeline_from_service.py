# -*- coding: utf-8 -*-
"""Воронка реализации идёт от услуги жёстко (владелец 13.11.2026): у сделки без своей воронки действует воронка услуги.

Поломка: бронь Альфарм-Таргета просит «выбрать воронку» (кнопка «Воронка», требование «Воронка реализации выбрана»
не выполнено, перевод в реализацию — «Не выбрана воронка реализации»), хотя у услуги воронка задана."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _deal_without_own_pipeline(db):
    from app.sales.models import SalesDeal
    did = db.execute(text("""SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id
                              WHERE d.realization_pipeline_id IS NULL AND s.realization_pipeline_id IS NOT NULL
                              ORDER BY d.id DESC LIMIT 1""")).scalar()
    if did is None:
        pytest.skip("на стенде нет сделки без своей воронки при воронке услуги")
    return db.get(SalesDeal, did)


def test_pipeline_check_passes_by_service(db):
    from app.sales.stage_checks import OK, REGISTRY, Ctx
    d = _deal_without_own_pipeline(db)
    assert REGISTRY["realization_pipeline"].fn(Ctx(db, d)).state == OK


def test_move_into_realization_does_not_ask_for_pipeline(db):
    from app.sales import stage_move
    from app.sales.catalog import Catalog
    d = _deal_without_own_pipeline(db)
    cat = Catalog(db)
    target = next(s for s in cat.by_id.values() if s.phase and s.phase.is_realization and not s.is_terminal)
    assert stage_move.plan_move(db, d, target, cat).needs_pipeline is False


def test_service_without_pipeline_still_asks(db):
    from app.sales.stage_checks import NOT_YET, REGISTRY, Ctx
    from app.sales.models import SalesDeal
    did = db.execute(text("""SELECT d.id FROM sales_deals d LEFT JOIN sales_services s ON s.id = d.service_id
                              WHERE d.realization_pipeline_id IS NULL AND s.realization_pipeline_id IS NULL
                              ORDER BY d.id DESC LIMIT 1""")).scalar()
    if did is None:
        pytest.skip("нет сделки без воронки у услуги")
    assert REGISTRY["realization_pipeline"].fn(Ctx(db, db.get(SalesDeal, did))).state == NOT_YET
