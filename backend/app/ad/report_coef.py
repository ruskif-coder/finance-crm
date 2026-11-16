# -*- coding: utf-8 -*-
"""Коэффициенты SIMB ID для отчёта клиенту (владелец 05.10.2026; настройки — routers/simb_id).

Правило владельца:
1. для каждой пары «площадка × креатив» (строка `ad_campaign_creative`) — разово на день;
2. частота и CTR = база ± случайная поправка в пределах заданного %, значение фиксируется
   (`report_daily_coef`, миграция 2026-10-05_report_daily_coef.sql) и больше не меняется —
   ни при повторной выгрузке, ни при правке настроек;
3. производные считаются от РЕАЛЬНЫХ показов: уники = показы ÷ частота, клики = показы × CTR;
4. на показы поправок нет.
5. (16.11.2026) расчётный охват: ещё два числа дня из диапазонов настроек — повторные заходы в рамках недели и пересечение
   аудитории площадок, %; фиксируются так же разово. Охват дня = уники × (1 − повторы) × (1 − пересечение).
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


def _range(settings: dict, lo: str, hi: str) -> float:
    a, b = float(settings.get(lo) or 0), float(settings.get(hi) or 0)
    return round(random.uniform(min(a, b), max(a, b)), 2)


def mid_reach(settings: dict) -> tuple:
    """Середины диапазонов — для показов, не разнесённых по креативам (у них нет своей строки коэффициентов)."""
    return ((float(settings.get("repeat_min") or 0) + float(settings.get("repeat_max") or 0)) / 2,
            (float(settings.get("overlap_min") or 0) + float(settings.get("overlap_max") or 0)) / 2)


def _row(r) -> dict:
    return {"freq": float(r[2]), "ctr_pct": float(r[3]),
            "repeat_pct": float(r[4]) if r[4] is not None else None, "overlap_pct": float(r[5]) if r[5] is not None else None}


def ensure(db: Session, keys: Iterable[Key], settings: dict) -> Dict[Key, dict]:
    """Коэффициенты для пар-дней: недостающие выбираются и фиксируются, имеющиеся — как есть.
    Возвращает {(креатив, день): {freq, ctr_pct, repeat_pct, overlap_pct}}."""
    keys = sorted(set(keys))
    if not keys:
        return {}
    ids = sorted({k[0] for k in keys})
    days = sorted({k[1] for k in keys})
    sql = text("""SELECT creative_id, date, freq, ctr_pct, repeat_pct, overlap_pct FROM report_daily_coef
                    WHERE creative_id = ANY(:i) AND date = ANY(:d)""")
    have = {(r[0], r[1]): _row(r) for r in db.execute(sql, {"i": ids, "d": days}).all()}
    missing = [k for k in keys if k not in have]
    if missing:   # одним пакетом (ревью 05.10.2026: по строке — тысячи запросов на РК)
        db.execute(text("""
            INSERT INTO report_daily_coef (creative_id, date, freq, ctr_pct, repeat_pct, overlap_pct, computed_at)
            VALUES (:c, :d, :f, :t, :r, :o, now())
            ON CONFLICT ON CONSTRAINT uq_report_coef_day DO NOTHING"""),
            [{"c": cid, "d": day,
              "f": max(0.01, _pick(settings["freq_base"], settings["freq_dev_pct"], 2)),
              "t": max(0.0, _pick(settings["ctr_base"], settings["ctr_dev_pct"], 4)),
              "r": _range(settings, "repeat_min", "repeat_max"), "o": _range(settings, "overlap_min", "overlap_max")}
             for cid, day in missing])
    # Дни, зафиксированные до 16.11.2026, — без чисел охвата: дозаполнить разово (только пустые, `IS NULL` — гонка безопасна)
    blank = [k for k, v in have.items() if v["repeat_pct"] is None or v["overlap_pct"] is None]
    if blank:
        db.execute(text("""
            UPDATE report_daily_coef SET repeat_pct = coalesce(repeat_pct, :r), overlap_pct = coalesce(overlap_pct, :o)
             WHERE creative_id = :c AND date = :d"""),
            [{"c": cid, "d": day, "r": _range(settings, "repeat_min", "repeat_max"),
              "o": _range(settings, "overlap_min", "overlap_max")} for cid, day in blank])
    if missing or blank:
        db.commit()
        # Перечитываем: при гонке двух выгрузок побеждает первая запись (DO NOTHING / coalesce).
        for r in db.execute(sql, {"i": ids, "d": days}).all():
            have[(r[0], r[1])] = _row(r)
    return {k: have[k] for k in keys if k in have}


def derive(shows: int, coef: dict) -> dict:
    """Производные от реальных показов пары за день."""
    shows = int(shows or 0)
    uniques = round(shows / coef["freq"]) if coef["freq"] else 0
    return {"uniques": uniques, "clicks": round(shows * coef["ctr_pct"] / 100),
            "reach": reach(uniques, coef.get("repeat_pct"), coef.get("overlap_pct"))}


def reach(uniques: float, repeat_pct, overlap_pct) -> float:
    """Охват дня: уники без повторных заходов в неделе и без пересечения аудитории площадок (без округления — суммируется)."""
    return float(uniques or 0) * (1 - float(repeat_pct or 0) / 100) * (1 - float(overlap_pct or 0) / 100)
