# -*- coding: utf-8 -*-
"""Расчёты годового плана без слоя HTTP.

Вынесено из `routers/year_plan.py` 07.10.2026: нужны крону `notify/scanner.py`. Роутер реэкспортирует имена.
"""
from typing import Optional
from app.sales.models import SalesYearPlanLine


def _month_items(line: SalesYearPlanLine, m: int) -> list:
    return [it for it in (line.products or {}).get(str(m), [])
            if isinstance(it, dict) and it.get("ref_id") is not None]

def _intended_amount(line: SalesYearPlanLine, m: int, items: Optional[list] = None) -> float:
    """Сумма (до НДС) месяца целиком или одной группы-сделки, если передан items."""
    src = _month_items(line, m) if items is None else items
    return round(sum(float(it.get("amount") or 0) for it in src), 2)

def _is_locked(line: SalesYearPlanLine, m: int) -> bool:
    """Замок месяца = полная заморозка: конвейер не создаёт и не пересобирает сделки
    этого месяца, а /match-deals не перетирает его пины. Правки в обе стороны стоят."""
    return bool((line.locks or {}).get(str(m)))

def _planned_months(line: SalesYearPlanLine) -> list:
    on = list(line.months_on or [])
    return [m for m in range(12) if m < len(on) and on[m] and _month_items(line, m)]
