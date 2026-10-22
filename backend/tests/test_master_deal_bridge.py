# -*- coding: utf-8 -*-
"""Мост мастер-сделка → операция (владелец 20.10.2026: «при наличии счёта формируем операцию», «операция = счёт»).

1С вернула номер счёта по комплекту УПД → одна операция «план поступлений» на этот счёт. Повтор не плодит дубль; сумма и номер
обновляются, пока операция не оплачена; оплаченную не трогаем. Без номера счёта (до 1С) — операции нет.
Живой пакет стенда, транзакция откатывается."""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import bridge as BR


@pytest.fixture
def env():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal, MasterDealUpd
    db = SessionLocal()
    k = db.query(MasterDealUpd).order_by(MasterDealUpd.id).first()
    if k is None:
        pytest.skip("на стенде нет комплектов УПД")
    # Счёт из 1С приходит только по подтверждённому ДС — номер ставим сами, не полагаясь на состояние пакета на стенде (откатывается).
    from app.sales.models import SalesAnnex
    a = db.get(SalesAnnex, k.annex_id)
    if a is not None and not a.number:
        a.number = "ДС № 2"
    try:
        yield db, db.get(MasterDeal, k.master_deal_id), k
    finally:
        db.rollback()
        db.close()


def _ops(db, k):
    return db.execute(text("SELECT id, status, income, invoice, invoice_date, ds_num, article_id, counterparty_id, period, description "
                           "FROM operations WHERE master_deal_upd_id = :k"), {"k": k.id}).all()


def test_no_invoice_no_operation(env):
    db, m, k = env
    k.onec_invoice_no = None
    assert BR.sync_kit(db, m, k) is None and not _ops(db, k)


def test_invoice_makes_one_planned_income_operation(env):
    db, m, k = env
    k.onec_invoice_no, k.onec_invoice_date = "1247", date(2026, 10, 31)
    op = BR.sync_kit(db, m, k)
    rows = _ops(db, k)
    assert len(rows) == 1
    r = rows[0]
    assert r.status == "план поступлений" and r.invoice == "1247" and r.invoice_date == date(2026, 10, 31)
    assert abs(r.income - float(k.gross)) < 0.01 and r.period == m.period
    assert r.article_id, "статья выручки — по основной услуге комплекта"
    assert r.counterparty_id and r.ds_num and r.description, "контрагент, № ДС и основание к закрытию"
    assert op.vat_fact and op.vat_rate, "НДС — как у любой операции, считается из суммы и ставки"


def test_repeat_updates_not_duplicates_and_paid_is_frozen(env):
    db, m, k = env
    k.onec_invoice_no = "1247"
    BR.sync_kit(db, m, k)
    k.onec_invoice_no, k.gross = "1248", float(k.gross) + 100
    BR.sync_kit(db, m, k)
    rows = _ops(db, k)
    assert len(rows) == 1 and rows[0].invoice == "1248" and abs(rows[0].income - float(k.gross)) < 0.01
    db.execute(text("UPDATE operations SET status = 'оплачено' WHERE id = :i"), {"i": rows[0].id})
    k.gross = float(k.gross) + 500
    BR.sync_kit(db, m, k)
    assert abs(_ops(db, k)[0].income - (float(k.gross) - 500)) < 0.01, "оплаченную операцию мост не трогает"


def test_main_service_by_amount():
    rows = [{"kind": "base", "position": "еФарм", "amount": 100.0}, {"kind": "base", "position": "Приоритезация", "amount": 300.0},
            {"kind": "extra", "position": "Комплект", "amount": 50.0}]
    assert BR.main_service(rows) == "Приоритезация"
    assert BR.main_service([{"kind": "extra", "position": "Комплект", "amount": 10.0}]) is None
