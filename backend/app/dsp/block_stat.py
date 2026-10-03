# -*- coding: utf-8 -*-
"""Суточные показы блока по умолчанию («кукуха2») из админки DSP → `dsp_block_stat`.

Владелец 03.10.2026: страница «Трафики → Статистика» показывает по РК «общую» стату и
«базу» — за вычетом «кукухи». Блок DSP цепляет к каждому нашему креативу сам, а по
кампаниям админка его не делит, поэтому храним сутки по блоку, а долю РК считает
`traffic/stats.py` по её суточным показам на площадке.

Какие блоки — `sales_publisher_surfaces.default_ms_block_id` (на поверхность свой).
Окно как у статистики DSP: вчера плюс два дня досчёта; повтор перезаписывает сутки.

Запуск: `python -m app.dsp.block_stat [--from 2026-10-01] [--to 2026-10-02]`.
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dsp import admin

log = logging.getLogger("finance.dsp")

LOOKBACK_DAYS = 3


def default_blocks(db: Session) -> Dict[str, Tuple[int, str]]:
    """id блока → (площадка, поверхность). Один блок у двух поверхностей — берётся первая."""
    out: Dict[str, Tuple[int, str]] = {}
    for bid, pid, kind in db.execute(text("""
        SELECT trim(default_ms_block_id), publisher_id, kind FROM sales_publisher_surfaces
         WHERE coalesce(trim(default_ms_block_id), '') <> '' ORDER BY id""")).all():
        out.setdefault(bid, (pid, kind))
    return out


def store_day(db: Session, day: date, shows: Dict[str, Tuple[int, int]],
              blocks: Dict[str, Tuple[int, str]]) -> int:
    n = 0
    for bid, (s, k) in shows.items():
        pid, kind = blocks.get(bid, (None, None))
        db.execute(text("""
            INSERT INTO dsp_block_stat (date, ms_block_id, publisher_id, surface, shows, clicks, fetched_at)
            VALUES (:d, :b, :p, :k, :s, :c, now())
            ON CONFLICT ON CONSTRAINT uq_dsp_block_stat DO UPDATE
               SET shows = EXCLUDED.shows, clicks = EXCLUDED.clicks,
                   publisher_id = EXCLUDED.publisher_id, surface = EXCLUDED.surface,
                   fetched_at = now()"""),
            {"d": day, "b": bid, "p": pid, "k": kind, "s": s, "c": k})
        n += 1
    db.commit()
    return n


def collect(db: Session, days: List[date], fetch=None) -> dict:
    """Снять и записать сутки. Сбой одного дня не останавливает остальные."""
    if fetch is None:
        if not admin.configured():
            return {"configured": False}
        fetch = admin.block_shows
    blocks = default_blocks(db)
    done, failed = [], []
    for day in days:
        try:
            done.append((day.isoformat(), store_day(db, day, fetch(day, list(blocks)), blocks)))
        except Exception as e:  # noqa: BLE001 — отчёт прогона, дальше следующий день
            db.rollback()
            log.warning("block_stat: %s не снят: %s", day, e)
            failed.append({"day": day.isoformat(), "error": str(e)[:200]})
    return {"configured": True, "blocks": len(blocks), "done": done, "failed": failed}


def window(today: Optional[date] = None) -> List[date]:
    today = today or date.today()
    return [today - timedelta(days=i) for i in range(LOOKBACK_DAYS, 0, -1)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    a = ap.parse_args(argv)
    if a.d_from:
        d0 = date.fromisoformat(a.d_from)
        d1 = date.fromisoformat(a.d_to) if a.d_to else date.today() - timedelta(days=1)
        days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    else:
        days = window()
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        out = collect(db, days)
    finally:
        db.close()
    print(out)
    return 1 if out.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
