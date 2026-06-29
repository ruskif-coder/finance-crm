"""
Тесты на compute_vat_fact (app/routers/operations.py) — формула выделения суммы
НДС "в том числе" из дохода/расхода. Раньше эта формула была продублирована
в 4 местах по отдельности (создание операции, одиночное и массовое редактирование,
импорт из Excel) и однажды уже расходилась между ними — отсюда и тесты именно
на этот кусок логики, см. CLAUDE.md ("vat_rate также триггерит пересчёт vat_fact").
"""
import pytest
from app.routers.operations import compute_vat_fact


def test_income_with_vat():
    # НДС 20% "в том числе" из дохода 1200 -> 200
    assert compute_vat_fact(income=1200, expense=0, vat_rate=20) == pytest.approx(200.0)


def test_expense_with_vat():
    assert compute_vat_fact(income=0, expense=1200, vat_rate=20) == pytest.approx(200.0)


def test_zero_vat_rate_returns_zero():
    assert compute_vat_fact(income=1000, expense=0, vat_rate=0) == 0


def test_no_income_no_expense_returns_zero():
    assert compute_vat_fact(income=0, expense=0, vat_rate=20) == 0


def test_income_takes_priority_over_expense():
    # Если почему-то заданы оба (в норме у операции либо доход, либо расход) —
    # формула считает по доходу первым, как и в исходной (продублированной) логике.
    assert compute_vat_fact(income=1200, expense=600, vat_rate=20) == pytest.approx(200.0)


def test_negative_vat_rate_treated_as_no_vat():
    assert compute_vat_fact(income=1000, expense=0, vat_rate=-5) == 0


@pytest.mark.parametrize("vat_rate,amount,expected", [
    (10, 1100, 100.0),
    (20, 1200, 200.0),
    (5, 1050, 50.0),
])
def test_various_rates(vat_rate, amount, expected):
    assert compute_vat_fact(income=amount, expense=0, vat_rate=vat_rate) == pytest.approx(expected)
