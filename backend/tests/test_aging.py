"""
Тесты на расчёт старения дебиторки/кредиторки (app/routers/reports.py):
_period_bounds, _term_days_for_counterparty, _due_date, _aging_bucket.
Эта логика общая для /reports/receivables, /balance/receivables, /balance/payables
и поля receivable_status в /operations — ошибка здесь расходится сразу по всем отчётам
(см. CLAUDE.md: "это реальная связанность между двумя роутерами").
"""
import pytest
from datetime import date, timedelta
from types import SimpleNamespace
from app.routers.reports import (
    _period_bounds,
    _term_days_for_counterparty,
    _due_date,
    _aging_bucket,
    DEFAULT_TERM_DAYS,
    GRACE_DAYS,
)


# ---- _period_bounds ----

def test_period_bounds_month_format():
    start, end = _period_bounds("2026-02")
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)  # 2026 - не високосный год


def test_period_bounds_leap_year_february():
    start, end = _period_bounds("2024-02")
    assert end == date(2024, 2, 29)


def test_period_bounds_quarter_format():
    start, end = _period_bounds("Q1 2026")
    assert start == date(2026, 1, 1)
    assert end == date(2026, 3, 31)


def test_period_bounds_q4_crosses_into_december():
    start, end = _period_bounds("Q4 2026")
    assert start == date(2026, 10, 1)
    assert end == date(2026, 12, 31)


def test_period_bounds_invalid_returns_none():
    assert _period_bounds("не период") == (None, None)
    assert _period_bounds(None) == (None, None)


# ---- _term_days_for_counterparty ----

def test_term_days_uses_explicit_value():
    cp = SimpleNamespace(term_days=90)
    assert _term_days_for_counterparty(cp) == 90


def test_term_days_falls_back_to_default_when_none():
    cp = SimpleNamespace(term_days=None)
    assert _term_days_for_counterparty(cp) == DEFAULT_TERM_DAYS


def test_term_days_falls_back_to_default_when_no_counterparty():
    assert _term_days_for_counterparty(None) == DEFAULT_TERM_DAYS


# ---- _due_date ----

def test_due_date_is_first_of_next_month_plus_term():
    term_days = 60
    due = _due_date("2026-01", term_days)
    # конец января -> 1 февраля -> +60 дней
    assert due == date(2026, 2, 1) + timedelta(days=term_days)


def test_due_date_zero_term_days_is_first_of_next_month():
    due = _due_date("2026-01", 0)
    assert due == date(2026, 2, 1)


def test_due_date_quarter_period():
    due = _due_date("Q1 2026", 60)
    assert due == date(2026, 4, 1) + timedelta(days=60)


def test_due_date_unparseable_period_returns_none():
    assert _due_date("мусор", 60) is None
    assert _due_date(None, 60) is None


# ---- _aging_bucket ----

def test_aging_bucket_future_when_due_date_ahead():
    today = date(2026, 6, 25)
    due = today + timedelta(days=10)
    assert _aging_bucket(due, today) == "future"


def test_aging_bucket_current_within_grace_period():
    today = date(2026, 6, 25)
    due = today - timedelta(days=GRACE_DAYS)  # ровно на границе буфера
    assert _aging_bucket(due, today) == "current"


def test_aging_bucket_overdue_past_grace_period():
    today = date(2026, 6, 25)
    due = today - timedelta(days=GRACE_DAYS + 1)
    assert _aging_bucket(due, today) == "overdue"


def test_aging_bucket_due_today_is_current():
    today = date(2026, 6, 25)
    assert _aging_bucket(today, today) == "current"


def test_aging_bucket_unknown_when_due_date_missing():
    assert _aging_bucket(None, date(2026, 6, 25)) == "unknown"
