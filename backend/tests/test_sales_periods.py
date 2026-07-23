"""
Тесты разбивки периода размещения по календарным месяцам.

Приём тот же, что в reports.py::expand_quarter_rows (квартал → 3 равных месяца):
сумма делится поровну между затронутыми месяцами. Остаток от округления
отдаётся последнему месяцу, чтобы сумма долей всегда совпадала с исходной —
иначе выручка «усыхает» на копейки при каждой агрегации.
"""
from datetime import date
from decimal import Decimal
import pytest
from app.sales.periods import split_amount_by_months


def test_single_month_returns_one_share():
    result = split_amount_by_months(date(2026, 5, 1), date(2026, 5, 31), Decimal("1000.00"))
    assert result == [("2026-05", Decimal("1000.00"))]


def test_partial_month_still_counts_as_that_month():
    result = split_amount_by_months(date(2026, 5, 10), date(2026, 5, 20), Decimal("300.00"))
    assert result == [("2026-05", Decimal("300.00"))]


def test_three_months_split_equally():
    result = split_amount_by_months(date(2026, 1, 1), date(2026, 3, 31), Decimal("300.00"))
    assert result == [
        ("2026-01", Decimal("100.00")),
        ("2026-02", Decimal("100.00")),
        ("2026-03", Decimal("100.00")),
    ]


def test_remainder_goes_to_last_month():
    result = split_amount_by_months(date(2026, 1, 1), date(2026, 3, 31), Decimal("100.00"))
    assert [m for m, _ in result] == ["2026-01", "2026-02", "2026-03"]
    assert [a for _, a in result] == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_sum_of_shares_always_equals_source():
    total = Decimal("1000.01")
    result = split_amount_by_months(date(2026, 1, 1), date(2026, 6, 30), total)
    assert sum(a for _, a in result) == total


def test_period_crossing_year_boundary():
    result = split_amount_by_months(date(2025, 11, 1), date(2026, 2, 28), Decimal("400.00"))
    assert [m for m, _ in result] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_zero_amount_produces_zero_shares():
    result = split_amount_by_months(date(2026, 1, 1), date(2026, 2, 28), Decimal("0"))
    assert [a for _, a in result] == [Decimal("0.00"), Decimal("0.00")]


def test_missing_period_to_defaults_to_calendar_month_of_from():
    result = split_amount_by_months(date(2026, 7, 15), None, Decimal("500.00"))
    assert result == [("2026-07", Decimal("500.00"))]


def test_missing_period_from_raises():
    with pytest.raises(ValueError):
        split_amount_by_months(None, date(2026, 7, 31), Decimal("500.00"))


def test_reversed_dates_raise():
    with pytest.raises(ValueError):
        split_amount_by_months(date(2026, 8, 1), date(2026, 7, 1), Decimal("500.00"))
