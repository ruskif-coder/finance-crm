# -*- coding: utf-8 -*-
"""План дня РК с учётом недокрута прошлых дней (владелец 13.10.2026).

Цель отчитанного дня = (план − факт ДО этого дня) ÷ дни до конца флайта, считая этот. РК не стартовала в срок —
каждый следующий день цель растёт; перекрут (в том числе после «темпа размещения») — снижает; ниже нуля не
уходит; в дни окна буста — плюс процент буста. Будущие дни — «нужно в день» (`flight.need_per_day`), как прежде.

То же правило считает «Отчёт по РК» на клиенте (`frontend/lib/rkAnalysis.mjs`, `planFor`): график и стена дней
на дашборде трафика обязаны показывать те же числа, поэтому тесты обоих держат одни и те же примеры
(`tests/test_day_plan.py` ↔ `lib/rkAnalysis.test.mjs`).
"""
from datetime import date, timedelta
from typing import Dict, Optional, Tuple


def past_goals(plan: float, fl, facts_by_day: Dict[date, Tuple], today: date,
               boost_pct: Optional[Dict[date, float]] = None) -> Dict[date, float]:
    """{день: цель дня} для дней флайта до `today` включительно. `facts_by_day` — {день: (показы, клики)}."""
    goals: Dict[date, float] = {}
    before = 0.0
    boost_pct = boost_pct or {}
    for i in range(fl.length):
        d = fl.date_from + timedelta(days=i)
        if d > today:
            break
        goals[d] = max(0.0, plan - before) / (fl.length - i) * (1 + boost_pct.get(d, 0) / 100.0)
        before += ((facts_by_day.get(d) or (0, 0))[0]) or 0
    return goals
