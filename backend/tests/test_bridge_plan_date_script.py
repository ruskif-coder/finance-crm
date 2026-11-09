# -*- coding: utf-8 -*-
"""Скрипт 2026-11-09_bridge_plan_date_empty (владелец 09.11.2026: «дата операции должна быть пустой»): у плана поступлений моста
«Дата» стирается, дата счёта остаётся. Ломается, если скрипт тронет оплаченную операцию моста, ручной план, дату счёта или
запишет что-то в сухом прогоне. Транзакция откатывается."""
import importlib

import pytest
from sqlalchemy import text

S = importlib.import_module("scripts.2026-11-09_bridge_plan_date_empty")


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    kits = s.execute(text("SELECT k.id FROM master_deal_upds k WHERE NOT EXISTS "
                          "(SELECT 1 FROM operations o WHERE o.master_deal_upd_id = k.id) ORDER BY k.id LIMIT 2")).scalars().all()
    if len(kits) < 2:
        pytest.skip("на стенде нет двух комплектов без операции")
    sql = text("INSERT INTO operations (status, income, expense, period, date, invoice_date, master_deal_upd_id) "
               "VALUES (:st, 100, 0, '2026-10', '2026-11-06', '2026-11-06', :k) RETURNING id")
    ids = [s.execute(sql, {"st": st, "k": k}).scalar()
           for st, k in (("ПЛАН ПОСТУПЛЕНИЙ", kits[0]), ("ОПЛАЧЕНО", kits[1]), ("ПЛАН ПОСТУПЛЕНИЙ", None))]
    try:
        yield s, ids
    finally:
        s.rollback()
        s.close()


def _dates(s, i):
    r = s.execute(text("SELECT date, invoice_date FROM operations WHERE id = :i"), {"i": i}).first()
    return (r.date and r.date.isoformat(), r.invoice_date and r.invoice_date.isoformat())


def test_dry_run_lists_bridge_plan_only_and_writes_nothing(db):
    s, (plan, paid, manual) = db
    ids = {x["id"] for x in S.run(s)}
    assert plan in ids and paid not in ids and manual not in ids
    assert _dates(s, plan) == ("2026-11-06", "2026-11-06")


def test_apply_clears_operation_date_keeps_invoice_date_and_is_idempotent(db):
    s, (plan, paid, manual) = db
    S.run(s, apply=True)
    assert _dates(s, plan) == (None, "2026-11-06")
    assert _dates(s, paid) == ("2026-11-06", "2026-11-06") and _dates(s, manual) == ("2026-11-06", "2026-11-06")
    assert plan not in {x["id"] for x in S.run(s)}
