# -*- coding: utf-8 -*-
"""Квартал: один разбор на все записи, один формат хранения.

БЫЛО (замер 07.10.2026). Квартал писали четырьмя способами, и каждый разбор знал только свой:
отчёты (5 мест) — только `Q1 2026`; импорт операций — `Q1 2026` и «1 квартал 2026», а период вида
`2025-Q1` и `2026 Q2` при загрузке файла без даты ТЕРЯЛСЯ молча; дашборд продаж — только год-впереди;
в базе при этом лежит одно: `Q1 2026` (124 операции) и `YYYY-MM`.

РЕШЕНИЕ ВЛАДЕЛЬЦА 07.10.2026: хранение не меняем (миграции нет), а все разборщики понимают все
написания, и ВСЕ ПОСЛЕДУЮЩИЕ записи приводятся к единому виду `Q1 2026` при записи — на уровне
модели `Operation.period`, а не в каждой ручке отдельно.

Этот файл держит правило: разбор — в `app/periods.py` и больше нигде.
"""
import pathlib
import re

import pytest

from app import periods

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

DIALECTS = [
    "Q1 2026", "q1 2026", "Q1  2026", "Q1-2026", "Q1/2026", "q1-2026",
    "2026-Q1", "2026-q1", "2026 Q1", "2026Q1", "2026 q1",
    "1 квартал 2026", "1-й квартал 2026", "1 кв-л 2026", "1 квартал 2026 г.", " Q1 2026 ",
]


@pytest.mark.parametrize("raw", DIALECTS)
def test_every_known_spelling_is_one_quarter(raw):
    assert periods.parse_quarter(raw) == (2026, 1), raw


@pytest.mark.parametrize("raw,want", [("Q4 2025", (2025, 4)), ("2025-Q2", (2025, 2)),
                                      ("3 квартал 2024", (2024, 3)), ("2027 q4", (2027, 4))])
def test_other_quarters_and_years(raw, want):
    assert periods.parse_quarter(raw) == want


@pytest.mark.parametrize("raw", ["", None, "2026-07", "2026-13", "Q5 2026", "Q0 2026", "5 квартал 2026",
                                 "Q1 26", "Q1", "2026", "март 2026", "разово*", "по итогам РК",
                                 "Q1 2026 Q2", "12026-Q1", "Q1 20260"])
def test_not_a_quarter(raw):
    assert periods.parse_quarter(raw) is None, raw


@pytest.mark.parametrize("raw", DIALECTS)
def test_stored_form_is_one_and_it_is_the_old_one(raw):
    assert periods.normalize_quarter(raw) == "Q1 2026"


def test_normalization_is_idempotent():
    for raw in DIALECTS:
        once = periods.normalize_period(raw)
        assert periods.normalize_period(once) == once


def test_normalize_period_leaves_everything_else_alone():
    for raw in ("2026-07", "2026-12", "", "разово*", "по итогам РК", "март 2026", None):
        assert periods.normalize_period(raw) == raw


def test_quarter_parts_keep_the_old_shape_for_the_report_code():
    """Отчёты берут ('Q1', '2026') — ключ для QUARTER_MONTHS и строку года."""
    assert periods.quarter_parts("2025-Q3") == ("Q3", "2025")
    assert periods.quarter_parts("2025-07") is None


def test_iso_form_for_exports():
    assert periods.iso_quarter(2025, 1) == "2025-Q1"


# ── запись приводится к одному виду на уровне модели ─────────────────────────

@pytest.mark.parametrize("raw,want", [("2025-Q1", "Q1 2025"), ("1 квартал 2026", "Q1 2026"),
                                      ("2026 Q2", "Q2 2026"), ("Q3 2026", "Q3 2026"),
                                      ("2026-07", "2026-07"), (None, None)])
def test_operation_period_is_stored_in_one_form(raw, want):
    from app.models import Operation
    op = Operation()
    op.period = raw
    assert op.period == want


def test_the_constructor_and_bulk_setattr_are_normalized_too():
    from app.models import Operation
    assert Operation(period="2025-Q4").period == "Q4 2025"
    op = Operation()
    for k, v in {"period": "2024 q2"}.items():       # так пишет массовая правка (setattr по словарю)
        setattr(op, k, v)
    assert op.period == "Q2 2024"


# ── читатели понимают все написания ──────────────────────────────────────────

def test_reports_expand_every_spelling_into_three_months():
    from app.routers.reports import expand_quarter_rows

    class Row:
        def __init__(self, period):
            self.period, self.bank = period, "Б"
            self.total_income, self.total_expense = 300.0, 90.0
    for raw in ("Q1 2025", "2025-Q1", "1 квартал 2025"):
        out = expand_quarter_rows([Row(raw)])
        assert [x["period"] for x in out] == ["2025-01", "2025-02", "2025-03"], raw
        assert out[0]["total_income"] == 100.0


def test_import_keeps_the_period_in_every_spelling_when_there_is_no_date():
    from app.routers.operations import _normalize_period
    for raw in DIALECTS:
        assert _normalize_period(raw, None) == "Q1 2026", raw


def test_import_still_prefers_the_real_date_over_a_stale_quarter():
    from datetime import date
    from app.routers.operations import _normalize_period
    assert _normalize_period("2025-Q1", date(2025, 7, 15)) == "2025-07"


def test_sales_dashboard_understands_both_orders():
    from app.routers.sales_dashboard import _parse_quarter
    a, b = _parse_quarter("2026-Q2"), _parse_quarter("Q2 2026")
    assert a is not None and a == b
    assert a[2] == "2026 Q2" and str(a[0]) == "2026-04-01" and str(a[1]) == "2026-07-01"
    assert _parse_quarter("мусор") is None and _parse_quarter(None) is None


# ── один разбор на проект ────────────────────────────────────────────────────

def test_no_other_module_keeps_its_own_quarter_regex():
    """Шестая копия — это ровно то, от чего избавлялись: правило расходится молча."""
    bad = []
    for f in APP.rglob("*.py"):
        if f.name == "periods.py" or "__pycache__" in f.parts:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\[Qq\]\(?\[1-4\]|Q\(?\[1-4\]|q\(\[1-4\]\)|кварт\\w", line) and "re." in line + "re.":
                if not line.lstrip().startswith("#"):
                    bad.append(f"{f.relative_to(APP)}:{n}: {line.strip()[:90]}")
    assert not bad, "свой разбор квартала вне app/periods.py:\n  " + "\n  ".join(bad)

# ── квартал внутри текста ячейки (ревью 07.10: строгий разбор терял «план Q1 2026») ──

IN_TEXT = ["план q1 2026", "Q1 2026 (прогноз)", "1 квартал 2026, план", "прогноз 1-i квартал 2026",
           "Выручка Q1-2026 факт", "1-й квартал 2026 г. (план)"]


@pytest.mark.parametrize("raw", IN_TEXT)
def test_quarter_is_found_inside_text(raw):
    assert periods.find_quarter(raw) == (2026, 1), raw


@pytest.mark.parametrize("raw", ["", None, "июль 2026", "план 2026", "Q5 2026", "кв 2026"])
def test_no_quarter_inside_text(raw):
    assert periods.find_quarter(raw) is None, raw


@pytest.mark.parametrize("raw", IN_TEXT)
def test_import_without_date_keeps_the_quarter_from_a_noisy_cell(raw):
    """Как было до 07.10: подстрока искалась re.search; строгий разбор молча давал None."""
    from app.routers.operations import _normalize_period
    assert _normalize_period(raw, None) == "Q1 2026", raw


@pytest.mark.parametrize("raw", ["Q1 2026", "2026-Q1", "1 квартал 2026"])
def test_receivables_bounds_understand_every_spelling(raw):
    from app.receivables import _period_bounds
    start, end = _period_bounds(raw)
    assert (str(start), str(end)) == ("2026-01-01", "2026-03-31"), raw
