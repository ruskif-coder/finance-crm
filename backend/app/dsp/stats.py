# -*- coding: utf-8 -*-
"""Съём статистики DSP за сутки: вызовы `Statistic.getPeriod` и разбор ответа.

Проект — `docs/ПРОЕКТ_сбор_статистики_DSP.md`. Всё, что здесь, выросло из замера
27.09.2026 со стенда, а не из документации:

* разбивки по дням в ответе нет — сутки = отдельный вызов с `from = to`;
* хеши кампаний, спрошенные вместе с креативами, МОЛЧА выпадают из ответа — поэтому два
  вызова на день: креативы пачками и отдельно кампании;
* `spent` приходит с хвостом плавающей точки (`4.8999999999999995`) — округляем до копеек;
* креатив без показов всё равно приходит с нулями.

ОТСУТСТВИЕ В ОТВЕТЕ — НЕ НОЛЬ. Хеш, который мы спросили и не получили, считается «нет
данных» и докладывается поимённо. Ноль на его месте выглядел бы правдой: площадка «не
крутила», и объём ушёл бы перераспределяться туда, где он и так откручен.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Optional

# Пачка хешей на один вызов. Проверено на 16; 100+ не пробовали — режем по 50, пока не
# проверим на живой РК (§8 проекта).
BATCH = 50


@dataclass(frozen=True)
class Numbers:
    shows: int
    clicks: int
    spend: Optional[Decimal]
    # Предложено сетью за сутки (`bid_statistic`); None — в ответе поля не было. Это «доступный
    # трафик» площадки, нужен для оценки темпа (`app/ad/pace`).
    offered: Optional[int] = None


@dataclass
class DayPull:
    day: date
    creatives: Dict[str, Numbers] = field(default_factory=dict)
    campaigns: Dict[str, Numbers] = field(default_factory=dict)
    missing_creatives: List[str] = field(default_factory=list)
    missing_campaigns: List[str] = field(default_factory=list)


def _int(v) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def _money(v) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError):
        return None


def parse(result: dict, asked: Iterable[str]) -> tuple:
    """Ответ → ({хеш: Numbers}, [спрошенные, но не пришедшие]).

    Ключ `total` — их сумма по запросу, в разбор не идёт. Регистр хешей у DSP верхний,
    у нас в базе бывает любой — сравниваем в верхнем."""
    got = {str(k).upper(): v for k, v in (result or {}).items()
           if k != "total" and isinstance(v, dict)}
    out, missing = {}, []
    for h in asked:
        v = got.get(h.upper())
        if v is None:
            missing.append(h)
            continue
        out[h.upper()] = Numbers(_int(v.get("show")), _int(v.get("click")),
                                 _money(v.get("spent")),
                                 _int(v.get("bid_statistic")) if "bid_statistic" in v else None)
    return out, missing


def _chunks(seq: List[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def pull_day(client, day: date, creatives: Iterable[str], campaigns: Iterable[str],
             batch: int = BATCH) -> DayPull:
    """Два вида вызовов на сутки: креативы пачками, кампании отдельно."""
    res = DayPull(day=day)
    cr = sorted({h.upper() for h in creatives if h})
    for part in _chunks(cr, batch):
        got, miss = parse(client.statistic_get_period(part, day, day), part)
        res.creatives.update(got)
        res.missing_creatives.extend(miss)
    camps = sorted({h.upper() for h in campaigns if h})
    for part in _chunks(camps, batch):
        got, miss = parse(client.statistic_get_period(part, day, day), part)
        res.campaigns.update(got)
        res.missing_campaigns.extend(miss)
    return res
