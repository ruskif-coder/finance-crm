# -*- coding: utf-8 -*-
"""Квартал: единственное место, где его разбирают и пишут.

До 07.10.2026 квартал писали четырьмя способами (`Q1 2026`, `2025-Q1`, `2026 Q2`, «1 квартал 2026»), и
каждый читатель знал только свой: отчёты — один, импорт — два, дашборд продаж — год-впереди. Период
вида `2025-Q1` при загрузке файла без даты терялся молча. В базе же лежит одно: `Q1 2026` (операции) и
`YYYY-MM`.

Решение владельца 07.10.2026: ХРАНЕНИЕ не меняем (`Q1 2026`, миграции нет), а
  · читатели понимают все написания — через `parse_quarter` / `quarter_parts`;
  · все последующие записи приводятся к `Q1 2026` при записи — `normalize_period` вызывает
    `Operation.period` (валидатор модели), чтобы это не зависело от того, какая ручка пишет.

Модуль не импортирует ничего из приложения: его зовут модели, отчёты и импорт.
"""
import re
from typing import Optional, Tuple

_YEAR_LO, _YEAR_HI = 1900, 2200

# «Q1 2026», «q1-2026», «Q1/2026», «Q1 2026 г.» (квартал впереди)
_Q_FIRST = re.compile(r"^\s*Q\s*([1-4])\s*[-/.\s]?\s*(\d{4})(?:\s*(?:г\.?|года))?\s*$", re.I)
# «2025-Q1», «2025 Q1», «2025Q1» (год впереди)
_Y_FIRST = re.compile(r"^\s*(\d{4})\s*[-/.\s]?\s*Q\s*([1-4])\s*$", re.I)
# «1 квартал 2026», «1-й квартал 2026 г.», «1 кв-л 2026», «1 кв. 2026»
_RU = re.compile(r"^\s*([1-4])\s*-?\s*(?:[йи]\s*)?кв(?:арт\w*|-?л\.?|\.)?\s*[-,.\s]*\s*(\d{4})(?:\s*(?:г\.?|года))?\s*$",
                 re.I)


# Те же написания, но КАК ПОДСТРОКА ячейки («план Q1 2026», «1 квартал 2026, план»). Импорт Excel
# получает такие ячейки без даты операции, и до 07.10.2026 квартал в них находился поиском по
# подстроке; строгий разбор молча давал None, и строка уходила без периода.
_Q_FIRST_IN = re.compile(r"Q\s*([1-4])(?!\d)\D{0,3}(\d{4})(?!\d)", re.I)
_Y_FIRST_IN = re.compile(r"(?<!\d)(\d{4})\s*[-/.\s]?\s*Q\s*([1-4])(?!\d)", re.I)
_RU_IN = re.compile(r"([1-4])\s*-?\s*(?:[йиi]\s*)?кв(?:арт\w*|-?л\.?|\.|(?![а-яё]))\D{0,10}(\d{4})(?!\d)", re.I)


def _ok(year: int) -> bool:
    return _YEAR_LO <= year <= _YEAR_HI


def parse_quarter(value) -> Optional[Tuple[int, int]]:
    """(год, номер квартала) из любого известного написания, иначе None."""
    if not isinstance(value, str):
        return None
    m = _Q_FIRST.match(value) or _RU.match(value)
    if m:
        q, year = int(m.group(1)), int(m.group(2))
        return (year, q) if _ok(year) else None
    m = _Y_FIRST.match(value)
    if m:
        year, q = int(m.group(1)), int(m.group(2))
        return (year, q) if _ok(year) else None
    return None


def find_quarter(value) -> Optional[Tuple[int, int]]:
    """(год, номер квартала) — из ячейки целиком ИЛИ из текста вокруг («план Q1 2026»), иначе None."""
    exact = parse_quarter(value)
    if exact or not isinstance(value, str):
        return exact
    m = _Q_FIRST_IN.search(value) or _RU_IN.search(value)
    if m:
        q, year = int(m.group(1)), int(m.group(2))
    else:
        m = _Y_FIRST_IN.search(value)
        if not m:
            return None
        year, q = int(m.group(1)), int(m.group(2))
    return (year, q) if _ok(year) else None


def format_quarter(year: int, q: int) -> str:
    """Вид, в котором квартал ХРАНИТСЯ: `Q1 2026` (его ждут отчёты, `QUARTER_MONTHS` и сортировка)."""
    return f"Q{q} {year}"


def iso_quarter(year: int, q: int) -> str:
    """Сортируемый вид для выгрузок и внутренних ключей: `2025-Q1`."""
    return f"{year}-Q{q}"


def normalize_quarter(value) -> Optional[str]:
    """Квартал в виде хранения или None, если это не квартал."""
    parsed = parse_quarter(value)
    return format_quarter(*parsed) if parsed else None


def normalize_period(value):
    """Период к виду хранения: квартал — `Q1 2026`, всё остальное (`YYYY-MM`, пусто, прочее) без изменений."""
    return normalize_quarter(value) or value


def quarter_parts(value) -> Optional[Tuple[str, str]]:
    """('Q1', '2026') — как отдавали группы старого регулярного выражения; для `QUARTER_MONTHS`."""
    parsed = parse_quarter(value)
    return (f"Q{parsed[1]}", str(parsed[0])) if parsed else None
