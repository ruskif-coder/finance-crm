# -*- coding: utf-8 -*-
"""Среднее время оплаты контрагента (владелец 18.11.2026): от 1-го числа месяца после периода до даты оплаты.

Поломки, которые ловит тест: счёт от срока с отсрочкой вместо начала следующего периода; квартал, отсчитанный от
следующего МЕСЯЦА; предоплата, обрезанная до нуля; среднее, взвешенное суммой, вместо простого.
"""
from datetime import date

import app.ad.models           # noqa: F401 — регистрирует таблицы
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.receivables import avg_pay_days


def test_month_period_counts_from_first_day_of_next_month():
    # период октябрь → отсчёт с 01.11; оплаты 11.11 (10 дн) и 21.11 (20 дн) → (10 + 20) / 2 = 15
    rows = [(1, '2026-10', date(2026, 11, 11)), (1, '2026-10', date(2026, 11, 21))]
    assert avg_pay_days(rows) == {1: (15, 2)}


def test_quarter_counts_from_day_after_quarter():
    # Q3 2026 → отсчёт с 01.10; оплата 31.10 → 30 дн, а не 61 (от 01.09)
    assert avg_pay_days([(2, 'Q3 2026', date(2026, 10, 31))]) == {2: (30, 1)}


def test_prepayment_stays_negative_and_rows_without_period_are_skipped():
    rows = [(3, '2026-12', date(2026, 11, 26)),     # предоплата за декабрь: от 01.01.2027 это −36 дн
            (3, None, date(2026, 11, 1)),
            (None, '2026-10', date(2026, 11, 5))]
    assert avg_pay_days(rows) == {3: (-36, 1)}


def test_receivables_report_carries_calc_day_and_usual_days():
    """Дебиторка: у каждой строки «текущий расчётный день» = сегодня − 1-е число следующего периода; «обычно платят» —
    число реестра контрагентов."""
    from datetime import date as d
    from app.database import SessionLocal
    from app.receivables import avg_pay_days_db, next_period_start
    from app.routers.reports import _compute_receivables
    db = SessionLocal()
    try:
        data, avg = _compute_receivables(db), avg_pay_days_db(db)
        ops = [(r['counterparty_id'], o) for r in data['rows'] for o in r['operations']]
        assert ops
        for cp, o in ops:
            nps = next_period_start(o['period'])
            assert o['calc_day'] == ((d.today() - nps).days if nps else None)
            assert o['usual_days'] == avg.get(cp, (None, 0))[0]
    finally:
        db.close()
