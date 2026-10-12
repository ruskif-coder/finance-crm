# -*- coding: utf-8 -*-
"""Дата из ячейки Excel — один разбор для импорта операций.

Наш формат — ДЕНЬ.МЕСЯЦ.ГОД («06.10.2026» — шестое октября). `pandas.to_datetime` читает
такую строку как МЕСЯЦ-ДЕНЬ и молча меняет их местами; при дне до 12 это июнь вместо октября,
при дне после 12 — пустая дата. Поэтому импорт зовёт только `parse_cell_date`, а `to_datetime`
в разборе файла запрещён тестом (tests/test_import_dates.py).

Понимает: настоящую дату Excel, строку «д.м.г» (разделители . / - пробел, год из 2 или 4 цифр),
ISO «гггг-мм-дд» (с временем или без), порядковый номер дня Excel. Пустое — None. Всё, что
прочитать нельзя, — ValueError: потерять дату молча хуже, чем остановить загрузку.
"""
import re
from datetime import date, datetime, timedelta
from typing import Optional

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$")
_DMY = re.compile(r"^(\d{1,2})[.\-/ ]+(\d{1,2})[.\-/ ]+(\d{2}|\d{4})(?:\s+г\.?)?(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")
_EXCEL_EPOCH = date(1899, 12, 30)


def _build(y: int, m: int, d: int, raw) -> date:
    try:
        return date(y, m, d)
    except ValueError:
        raise ValueError(f"Не удалось прочитать дату «{raw}»: такого числа нет в календаре") from None


def parse_cell_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):          # pandas.Timestamp — тоже datetime
        return None if value != value else value.date()      # NaT != NaT
    if isinstance(value, date):
        return value
    if isinstance(value, float) and value != value:           # NaN
        return None
    if isinstance(value, (int, float)):
        if 20000 < value < 80000:            # 1954…2118 — порядковый день Excel
            return _EXCEL_EPOCH + timedelta(days=int(value))
        raise ValueError(f"Не удалось прочитать дату «{value}»")
    s = str(value).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return None
    m = _ISO.match(s)
    if m:
        return _build(int(m.group(1)), int(m.group(2)), int(m.group(3)), s)
    m = _DMY.match(s)
    if m:
        y = int(m.group(3))
        if y < 100:
            y += 2000
        return _build(y, int(m.group(2)), int(m.group(1)), s)
    raise ValueError(f"Не удалось прочитать дату «{s}». Формат — день.месяц.год, например 06.10.2026")
