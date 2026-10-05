# -*- coding: utf-8 -*-
"""Коэффициенты SIMB ID для отчёта клиенту (владелец 05.10.2026; настройки — routers/simb_id).

Правило владельца:
1. для каждой пары «площадка × креатив» (строка `ad_campaign_creative`) — разово на день;
2. частота и CTR = база ± случайная поправка в пределах заданного %, значение фиксируется
   (`report_daily_coef`, миграция 2026-10-05_report_daily_coef.sql) и больше не меняется —
   ни при повторной выгрузке, ни при правке настроек;
3. производные считаются от РЕАЛЬНЫХ показов: уники = показы ÷ частота, клики = показы × CTR;
4. на показы поправок нет.
"""
from __future__ import annotations

import random
from datetime import date
from typing import Dict, Iterable, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

Key = Tuple[int, date]


def _pick(base: float, dev_pct: float, digits: int) -> float:
    if not dev_pct:
        return round(float(base), digits)
    k = 1 + random.uniform(-dev_pct, dev_pct) / 100
    return round(float(base) * k, digits)


def ensure(db: Session, keys: Iterable[Key], settings: dict) -> Dict[Key, dict]:
    """Коэффициенты для пар-дней: недостающие выбираются и фиксируются, имеющиеся — как есть.
    Возвращает {(креатив, день): {freq, ctr_pct}}."""
    keys = sorted(set(keys))
    if not keys:
        return {}
    ids = sorted({k[0] for k in keys})
    days = sorted({k[1] for k in keys})
    have = {(r[0], r[1]): {"freq": float(r[2]), "ctr_pct": float(r[3])} for r in db.execute(text("""
        SELECT creative_id, date, freq, ctr_pct FROM report_daily_coef
         WHERE creative_id = ANY(:i) AND date = ANY(:d)"""), {"i": ids, "d": days}).all()}
    missing = [k for k in keys if k not in have]
    if missing:   # одним пакетом (ревью 05.10.2026: по строке — тысячи запросов на РК)
        db.execute(text("""
            INSERT INTO report_daily_coef (creative_id, date, freq, ctr_pct, computed_at)
            VALUES (:c, :d, :f, :t, now())
            ON CONFLICT ON CONSTRAINT uq_report_coef_day DO NOTHING"""),
            [{"c": cid, "d": day,
              "f": max(0.01, _pick(settings["freq_base"], settings["freq_dev_pct"], 2)),
              "t": max(0.0, _pick(settings["ctr_base"], settings["ctr_dev_pct"], 4))}
             for cid, day in missing])
    if missing:
        db.commit()
        # Перечитываем: при гонке двух выгрузок побеждает первая запись (DO NOTHING).
        for r in db.execute(text("""
            SELECT creative_id, date, freq, ctr_pct FROM report_daily_coef
             WHERE creative_id = ANY(:i) AND date = ANY(:d)"""), {"i": ids, "d": days}).all():
            have[(r[0], r[1])] = {"freq": float(r[2]), "ctr_pct": float(r[3])}
    return {k: have[k] for k in keys if k in have}


def derive(shows: int, coef: dict) -> dict:
    """Производные от реальных показов пары за день."""
    shows = int(shows or 0)
    return {"uniques": round(shows / coef["freq"]) if coef["freq"] else 0,
            "clicks": round(shows * coef["ctr_pct"] / 100)}
