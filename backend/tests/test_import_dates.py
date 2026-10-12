# -*- coding: utf-8 -*-
"""Даты при импорте операций: день.месяц.год, а не месяц-день (12.10.2026, третий повтор).

Файл владельца хранит «Счет от дата» ТЕКСТОМ «06.10.2026»; `pandas.to_datetime` читал его как
6 июня. Правило — в `app/import_dates.py`, и импорт не вправе звать `to_datetime` на ячейках.
"""
import pathlib
from datetime import date, datetime

import pytest

from app.import_dates import parse_cell_date

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


@pytest.mark.parametrize("raw,want", [
    ("06.10.2026", date(2026, 10, 6)),          # день до 12 — как раз случай, который путали
    ("07.10.2026", date(2026, 10, 7)),
    ("12.10.2026", date(2026, 10, 12)),
    ("25.09.2026", date(2026, 9, 25)),          # день после 12 раньше терялся
    ("1.2.2026", date(2026, 2, 1)),
    ("06/10/2026", date(2026, 10, 6)),
    ("06-10-2026", date(2026, 10, 6)),
    ("06 10 2026", date(2026, 10, 6)),
    ("06.10.26", date(2026, 10, 6)),
    (" 06.10.2026 ", date(2026, 10, 6)),
    ("06.10.2026 г.", date(2026, 10, 6)),
    ("06.10.2026 14:30", date(2026, 10, 6)),
    ("2026-10-06", date(2026, 10, 6)),
    ("2026-10-06 00:00:00", date(2026, 10, 6)),
    (datetime(2026, 10, 6, 0, 0), date(2026, 10, 6)),
    (date(2026, 10, 6), date(2026, 10, 6)),
    (46301, date(2026, 10, 6)),                 # порядковый день Excel
])
def test_dates_read_day_first(raw, want):
    assert parse_cell_date(raw) == want


@pytest.mark.parametrize("raw", [None, "", "  ", "nan", float("nan")])
def test_empty_is_none(raw):
    assert parse_cell_date(raw) is None


def test_pandas_timestamp_and_nat():
    import pandas as pd
    assert parse_cell_date(pd.Timestamp("2026-10-06")) == date(2026, 10, 6)
    assert parse_cell_date(pd.NaT) is None


@pytest.mark.parametrize("raw", ["31.02.2026", "13.13.2026", "вчера", "06.10", "2026/10/06x", 5])
def test_unreadable_stops_instead_of_guessing(raw):
    with pytest.raises(ValueError):
        parse_cell_date(raw)


def test_import_does_not_call_to_datetime_on_cells():
    src = (APP / "routers" / "operations.py").read_text(encoding="utf-8")
    assert "to_datetime(" not in src, "даты ячеек — только через app.import_dates.parse_cell_date"
