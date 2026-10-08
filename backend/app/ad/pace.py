# -*- coding: utf-8 -*-
"""Оценка темпа площадки в РК (владелец 08.10.2026; задача отложена 05.10, см. память).

Для каждой площадки за последние сутки: сравнить её показы с тем, что НУЖНО в день, и сказать, что
мешает — нет трафика или мы не открутили. «Нужно в день» на каждые сутки считается так же, как в
`flight.need_per_day`: (план площадки − открутила до этих суток) ÷ дней от этих суток до конца.

Статусы суток (порог 10 % — как в записанном правиле):

  · «нет трафика»             — сеть не предложила ничего и показов нет (сайт лежит, снят код, блок);
  · «перебор»                 — показов больше 110 % нужного;
  · «в темпе»                 — не меньше 90 % нужного (или нужного уже нет — план закрыт);
  · «мало трафика»            — меньше 90 %, и предложено меньше нужного: реальная возможность площадки;
  · «трафик есть, не открутили» — меньше 90 %, предложено не меньше нужного: темп, частота, другая РК, креатив;
  · «недобор»                 — меньше 90 %, а предложенного не знаем (Adfox, нет `bid_statistic`) — без причины.

«Хронический недобор» — недобор в 3 из последних 5 суток с данными. «Возможность в день» — медиана
предложенного за те же сутки: ориентир для будущего планировщика. Функции чистые: БД не трогают.
"""
from datetime import date, timedelta
from statistics import median
from typing import Dict, Optional, Tuple

LOW, HIGH = 0.9, 1.1
WINDOW = 5
CHRONIC = 3

IN_PACE, OVER, NO_TRAFFIC, LITTLE, NOT_DELIVERED, SHORT = (
    "в темпе", "перебор", "нет трафика", "мало трафика", "трафик есть, не открутили", "недобор")
UNDER = (NO_TRAFFIC, LITTLE, NOT_DELIVERED, SHORT)


def need_on(plan: float, fact_before: float, day: date, date_end: date) -> float:
    """Сколько нужно показать в эти сутки: остаток плана ÷ дней от них до конца флайта (включительно)."""
    left = (date_end - day).days + 1
    return max(0.0, plan - fact_before) / left if left > 0 else 0.0


def status_of(shows: float, offered: Optional[float], need: float) -> str:
    if need <= 0:
        return IN_PACE
    if offered is not None and offered <= 0 and shows <= 0:
        return NO_TRAFFIC
    if shows > need * HIGH:
        return OVER
    if shows >= need * LOW:
        return IN_PACE
    if offered is None:
        return SHORT
    return LITTLE if offered < need else NOT_DELIVERED


def assess(plan: Optional[float], days: Dict[date, Tuple[int, Optional[int]]],
           date_end: Optional[date], as_of: Optional[date]) -> Optional[dict]:
    """Темп площадки: {status, day, shows, offered, need, chronic, capacity} или None (оценивать нечем).

    `days` — {сутки: (показы, предложено или None)} с начала РК; `as_of` — последние отчитанные сутки."""
    if not plan or not date_end or not as_of or not days:
        return None
    last = max((d for d in days if d <= as_of), default=None)
    if last is None:
        return None
    rows, cum = [], 0
    for d in sorted(x for x in days if x <= as_of):
        shows, offered = days[d]
        rows.append((d, shows, offered, need_on(plan, cum, d, date_end)))
        cum += shows
    recent = [r for r in rows if r[0] > as_of - timedelta(days=WINDOW)]
    statuses = [status_of(s, o, n) for _d, s, o, n in recent]
    d, shows, offered, need = rows[-1]
    known = [o for _d, _s, o, _n in recent if o is not None]
    return {"status": statuses[-1] if recent else IN_PACE, "day": d, "shows": shows, "offered": offered,
            "need": round(need), "chronic": sum(1 for s in statuses if s in UNDER) >= CHRONIC,
            "capacity": round(median(known)) if known else None}
