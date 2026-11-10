# -*- coding: utf-8 -*-
"""«Выбрано» по кредитной линии — из операций (владелец 10.11.2026: «как в операциях синхронизировать, чтобы висело в ДДС»).

Линия с банком-контрагентом: оплаченный приход − оплаченный расход по статьям тела кредита (разметка `loan_body`) с этим
контрагентом. План не считается: деньги ещё не взяты и не возвращены (плановый возврат и так виден в ДДС будущим расходом).
Проценты — в «КРЕДИТАХ», не тело. Линия без контрагента — ручное `used_amount` (заморожено, миграция 2026-11-10).
Одна функция на настройки и «Деньги на сегодня» (`pay_plan_summary`)."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import PAID


def used_of(db: Session, lines) -> dict:
    """{id линии: выбрано}."""
    cps = [c.counterparty_id for c in lines if c.counterparty_id]
    by_cp = {}
    if cps:
        by_cp = dict(db.execute(text("""
            SELECT o.counterparty_id, coalesce(sum(coalesce(o.income, 0) - coalesce(o.expense, 0)), 0)
              FROM operations o JOIN articles a ON a.id = o.article_id
             WHERE a.pl_line = 'loan_body' AND o.status = :paid AND o.counterparty_id = ANY(:cps)
             GROUP BY o.counterparty_id"""), {"paid": PAID, "cps": cps}).all())
    return {c.id: float(by_cp.get(c.counterparty_id, 0)) if c.counterparty_id else float(c.used_amount or 0) for c in lines}
