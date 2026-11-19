# -*- coding: utf-8 -*-
"""Дебиторка (владелец 18.11.2026): сальдо взаимных обязательств и документы операций для «глаза».

Ломается, если: сальдо считает план оплат по ВСЕМ контрагентам или берёт оплаченное; знак перевёрнут (плюс должен значить
«нам должны»); операция моста мастер-сделки потеряла ссылку на свой ДС; ручной операции приписан чужой документ.
"""
import app.ad.models           # noqa: F401 — регистрирует таблицы
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Operation
from app.routers.reports import _compute_receivables


def test_balance_is_receivable_minus_our_planned_payments():
    db = SessionLocal()
    try:
        data = _compute_receivables(db)
        assert data['rows']
        for r in data['rows']:
            payable = db.query(func.coalesce(func.sum(Operation.expense), 0)).filter(
                Operation.status == 'ПЛАН ОПЛАТ', Operation.counterparty_id == r['counterparty_id']).scalar()
            assert abs(r['mutual'] - float(payable)) < 0.01
            assert abs(r['balance'] - (r['amount'] - float(payable))) < 0.01
    finally:
        db.close()


def test_docs_only_for_bridge_operations():
    db = SessionLocal()
    try:
        ops = [o for r in _compute_receivables(db)['rows'] for o in r['operations']]
        bridged = {i for (i,) in db.query(Operation.id).filter(Operation.master_deal_upd_id.isnot(None)).all()}
        for o in ops:
            assert (o['docs'] is not None) == (o['id'] in bridged), o['id']
            if o['docs']:
                assert o['docs']['annex_id'] and o['docs']['kit_id']
    finally:
        db.close()


def test_manager_is_account_of_latest_paying_deal():
    """Ответственный — аккаунт последней сделки, где контрагент платит; без сделок с аккаунтом — пусто, а не чужое имя."""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        for r in _compute_receivables(db)['rows']:
            want = db.execute(text("""SELECT r.name FROM sales_deals d JOIN sales_reps r ON r.id = d.account_manager_id
                WHERE coalesce(d.payer_counterparty_id, d.counterparty_id) = :c ORDER BY d.id DESC LIMIT 1"""),
                {"c": r['counterparty_id']}).scalar()
            assert r['manager'] == want
    finally:
        db.close()
