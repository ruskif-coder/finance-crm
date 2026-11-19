# -*- coding: utf-8 -*-
"""Экран «Деньги» (18.11.2026): цифры обязаны сходиться с отчётами, а допущения — не выдумывать данных.

Поломки, которые ловят тесты:
· остаток на счетах посчитан своей формулой и разошёлся с карточками ДДС;
· «как платят на деле» считает задержку своей формулой и расходится с колонкой «Опл.» реестра контрагентов;
· транш цепочки оплат (общий корень) показан в «Качестве данных» как дубль;
· план оплат без даты тихо попал в календарь на сегодня (их десятки — герой ушёл бы в минус на 40 млн).
"""
from datetime import date

import pytest

import app.ad.models           # noqa: F401 — регистрирует таблицы в Base.metadata
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.money import overview as mo
from app.routers.reports import get_dds_summary

TODAY = date(2026, 11, 18)


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.rollback()
    d.close()


def test_usual_date_is_next_period_start_plus_registry_average(db):
    """«Как платят на деле» = 1-е число следующего периода + то же среднее, что колонка «Опл.» реестра. Своей формулы нет."""
    from datetime import timedelta
    from app.receivables import avg_pay_days_db, next_period_start
    data = mo.build(db, TODAY)
    avg = avg_pay_days_db(db)
    checked = 0
    for p in data['plans']:
        if p['kind'] != 'in' or p['cp_id'] not in avg or not next_period_start(p['period']):
            continue
        assert p['usual'] == next_period_start(p['period']) + timedelta(days=avg[p['cp_id']][0])
        assert p['delay'] == (p['usual'] - p['due']).days
        checked += 1
    assert checked > 0


def test_duplicates_same_counterparty_and_sum_within_three_days():
    rows = [(10, 7, 1000.0, date(2026, 11, 1), 10),
            (11, 7, 1000.0, date(2026, 11, 4), 11),     # +3 дня — похоже на дубль
            (12, 7, 1000.0, date(2026, 11, 9), 12),     # +5 дней от предыдущего — уже нет
            (13, 8, 1000.0, date(2026, 11, 1), 13)]     # другой контрагент
    assert mo.duplicate_pairs(rows) == {10, 11}


def test_tranches_of_one_chain_are_not_duplicates():
    rows = [(20, 7, 500.0, date(2026, 11, 1), 20),
            (21, 7, 500.0, date(2026, 11, 1), 20)]      # часть цепочки с корнем 20
    assert mo.duplicate_pairs(rows) == set()


def test_short_name_drops_legal_form_and_quotes():
    assert mo.short_name('АЛЬФАРМ ООО') == 'АЛЬФАРМ'
    assert mo.short_name('АО «ДИДЖИТАЛ АЛЬЯНС»') == 'ДИДЖИТАЛ АЛЬЯНС'
    assert mo.short_name(None) == '—'


def test_balance_matches_dds_cards(db):
    """Остаток на счетах экрана = сумма карточек банков в ДДС: одна и та же формула (стартовый + оплаченное)."""
    data = mo.build(db, TODAY)
    dds = get_dds_summary(db=db, current_user=None)
    assert data['balance_total'] == pytest.approx(dds['total_balance'], abs=0.01)
    assert {a['bank']: round(a['balance'], 2) for a in data['accounts']} == \
        {b['bank']: round(b['balance'], 2) for b in dds['by_bank']}


def test_every_plan_has_a_date_and_undated_payments_are_counted_apart(db):
    from app.models import Operation
    data = mo.build(db, TODAY)
    assert all(p['due'] is not None for p in data['plans'] if p['kind'] == 'out')
    undated = db.query(Operation).filter(Operation.status == 'ПЛАН ОПЛАТ', Operation.date.is_(None),
                                         Operation.expense > 0).count()
    assert data['undated_out']['count'] == undated
    assert all(p['kind'] == 'in' for p in data['plans'] if p['delay'])   # задержка — только у поступлений
