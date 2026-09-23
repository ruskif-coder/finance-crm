# -*- coding: utf-8 -*-
"""Прибор: требование «Приложение сформировано» видит настоящие приложения (аудит 23.09, 3.H2).

Проверка читала `SalesDeal.annex_id` — колонку, которую не пишет НИ ОДИН путь кода: связь
сделки с приложением живёт в `sales_deal_annex_allocation`. Замер на стенде: требование
блокирующее, `annex_id` заполнен у 0 из 948 сделок. Стадия «Согласование ДС» была заперта
для всех, кроме мастера, — и выглядело это как «приложение не собрано», хотя оно было.
"""
import pathlib

import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.sales import stage_checks as sc
from app.sales.models import SalesAnnex, SalesDeal, SalesDealAnnexAllocation


def _run(db, deal):
    return sc.REGISTRY["annex_generated"].fn(sc.Ctx(db, deal))


def test_allocated_annex_counts_as_generated():
    """Разнесение по приложению — в транзакции с откатом: на стенде их может не быть."""
    from app.models import Contract
    db = SessionLocal()
    db.commit = db.flush
    try:
        contract = db.query(Contract).first()
        deal = db.query(SalesDeal).first()
        if contract is None or deal is None:
            pytest.skip("нужны договор и сделка")
        annex = SalesAnnex(contract_id=contract.id, total_amount=1000.0, currency="RUB")
        db.add(annex)
        db.flush()
        db.add(SalesDealAnnexAllocation(deal_id=deal.id, annex_id=annex.id, amount=1000.0))
        db.flush()
        assert _run(db, deal).state == sc.OK
    finally:
        db.rollback()
        db.close()


def test_deal_without_annex_is_not_yet():
    db = SessionLocal()
    db.commit = db.flush
    try:
        has = db.query(SalesDealAnnexAllocation.deal_id)
        deal = db.query(SalesDeal).filter(SalesDeal.id.notin_(has)).first()
        if deal is None:
            pytest.skip("нет сделки без приложения")
        assert _run(db, deal).state == sc.NOT_YET
    finally:
        db.close()


def test_the_dead_column_is_not_read():
    src = pathlib.Path(sc.__file__).read_text(encoding="utf-8")
    assert "deal.annex_id" not in src, "проверка снова читает мёртвую колонку SalesDeal.annex_id"
    assert SalesAnnex  # модель на месте — связь идёт через разнесение
