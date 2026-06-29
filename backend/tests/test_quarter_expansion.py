"""
Тесты на expand_quarter_rows (app/routers/reports.py) — разбивает квартальные
периоды ("Q1 2026") на 3 равных месяца для графиков/таблиц, которые группируют
по месяцу. Эта логика дублирована в нескольких местах (operations.py,
reports.py: /dds, /pl, /plan-fact) и уже несколько раз ломалась на проде
(см. историю задач #43-46 "квартальный формат периода").
"""
from types import SimpleNamespace
from app.routers.reports import expand_quarter_rows


def _row(period, bank="АльфаБанк", total_income=0, total_expense=0):
    return SimpleNamespace(period=period, bank=bank, total_income=total_income, total_expense=total_expense)


def test_non_quarter_row_passes_through_unchanged():
    rows = [_row("2026-05", total_income=1000, total_expense=400)]
    result = expand_quarter_rows(rows)
    assert result == [{
        "period": "2026-05",
        "bank": "АльфаБанк",
        "total_income": 1000,
        "total_expense": 400,
    }]


def test_quarter_row_expands_into_three_months():
    rows = [_row("Q1 2026", total_income=300, total_expense=90)]
    result = expand_quarter_rows(rows)
    assert [r["period"] for r in result] == ["2026-01", "2026-02", "2026-03"]
    for r in result:
        assert r["total_income"] == 100  # 300 / 3
        assert r["total_expense"] == 30  # 90 / 3
        assert r["bank"] == "АльфаБанк"


def test_q4_maps_to_oct_nov_dec():
    rows = [_row("Q4 2026", total_income=300, total_expense=0)]
    result = expand_quarter_rows(rows)
    assert [r["period"] for r in result] == ["2026-10", "2026-11", "2026-12"]


def test_none_amounts_treated_as_zero():
    rows = [_row("2026-05", total_income=None, total_expense=None)]
    result = expand_quarter_rows(rows)
    assert result[0]["total_income"] == 0
    assert result[0]["total_expense"] == 0


def test_none_amounts_in_quarter_row_treated_as_zero():
    rows = [_row("Q2 2026", total_income=None, total_expense=None)]
    result = expand_quarter_rows(rows)
    assert all(r["total_income"] == 0 and r["total_expense"] == 0 for r in result)


def test_empty_period_passes_through():
    rows = [_row(None, total_income=50, total_expense=0)]
    result = expand_quarter_rows(rows)
    assert result == [{"period": "", "bank": "АльфаБанк", "total_income": 50, "total_expense": 0}]


def test_multiple_rows_mixed():
    rows = [
        _row("2026-01", total_income=10, total_expense=5),
        _row("Q1 2026", total_income=30, total_expense=0),
    ]
    result = expand_quarter_rows(rows)
    # 1 обычная строка + 3 развёрнутых из квартала = 4
    assert len(result) == 4
    assert result[0]["period"] == "2026-01"
    assert [r["period"] for r in result[1:]] == ["2026-01", "2026-02", "2026-03"]
