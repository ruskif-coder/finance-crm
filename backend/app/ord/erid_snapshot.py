# -*- coding: utf-8 -*-
"""Снимок разреза «площадка × креатив» за месяц для отчёта ОРД (владелец 11.11.2026).

Сырьё DSP по креативу (`dsp_stat_raw`) хранится месяц (`drop_after 1 month`), суточная сводка разреза по креативу не держит —
без снимка показы площадки через пару недель после конца месяца не разделить по ЕРИД. Крон раз в сутки снимает текущий и
прошлый месяц: DSP — через карту хешей (`stat_store.hash_map`, с перевыгрузками), Adfox — `adfox_creative_stat`.
Запись только растёт: часть сырья уже удалена — новый прогон даст меньше, и такой снимок прежний не перетирает.

    python -m app.ord.erid_snapshot                                    # текущий и прошлый месяц
    python -m app.ord.erid_snapshot --month 2026-10                    # один месяц
    python -m app.ord.erid_snapshot --month 2026-10 --csv FILE.csv     # сырьё DSP из сохранённой выгрузки (ts,ms_campaign_xxhash,
                                                                       #   ms_source_key,ms_creative_xxhash,shows,clicks,...)
"""
import app.model_registry  # noqa: F401  — крон отдельным процессом: внешние ключи должны находиться

import argparse
import csv
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ord.month_report import month_bounds

log = logging.getLogger("finance.ord")
MSK = timezone(timedelta(hours=3))


def _campaigns(db: Session, d1: date, d2: date) -> list:
    from app.ad.stat_sources import fact_sources
    return [r[0] for r in db.execute(text("""SELECT DISTINCT campaign_id FROM ad_campaign_stat
                                               WHERE source = ANY(:s) AND date BETWEEN :a AND :b AND shows > 0"""),
                                     {"s": fact_sources(), "a": d1, "b": d2})]


def _dsp_rows(dsp_db, hashes: list, d1: date, d2: date) -> Iterable[tuple]:
    return dsp_db.execute(text("""
        SELECT ms_creative_xxhash, sum(shows), sum(clicks) FROM dsp_stat_raw
         WHERE ms_campaign_xxhash = ANY(:h) AND ms_source_key IS NULL AND ms_creative_xxhash IS NOT NULL
           AND (ts AT TIME ZONE 'Europe/Moscow')::date BETWEEN :a AND :b
         GROUP BY 1"""), {"h": hashes, "a": d1, "b": d2}).all()


def _csv_rows(path: str, hashes: list, d1: date, d2: date) -> Iterable[tuple]:
    want, acc = set(hashes), {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("ms_source_key") or "").strip() or not r.get("ms_creative_xxhash"):
                continue
            if (r["ms_campaign_xxhash"] or "").upper() not in want:
                continue
            day = datetime.fromisoformat(r["ts"].replace("+00", "+00:00")).astimezone(MSK).date()
            if d1 <= day <= d2:
                a = acc.setdefault(r["ms_creative_xxhash"].upper(), [0, 0])
                a[0] += int(float(r["shows"] or 0))
                a[1] += int(float(r["clicks"] or 0))
    return [(h, v[0], v[1]) for h, v in acc.items()]


def collect(db: Session, dsp_db, month: date, csv_path: Optional[str] = None) -> Dict[int, list]:
    """{строка креатива: [показы, клики]} за месяц — DSP (или CSV) + Adfox."""
    d1, d2 = month_bounds(month)
    ids = _campaigns(db, d1, d2)
    out: Dict[int, list] = {}
    if ids and (dsp_db is not None or csv_path):
        from app.dsp import stat_store
        from app.dsp.client import PROD, MsClient
        cl = MsClient(contour=PROD)
        hmap = stat_store.hash_map(db, dsp_db, ids, contour=cl.contour, partner=cl.partner_xxhash)
        hashes = list(hmap.campaigns)
        rows = _csv_rows(csv_path, hashes, d1, d2) if csv_path else _dsp_rows(dsp_db, hashes, d1, d2)
        for cr, shows, clicks in rows:
            rid = hmap.rows.get((cr or "").upper())
            if rid is not None:
                acc = out.setdefault(rid, [0, 0])
                acc[0] += int(shows or 0)
                acc[1] += int(clicks or 0)
    for cid, shows, clicks in db.execute(text("""SELECT creative_id, sum(shows), sum(clicks) FROM adfox_creative_stat
                                                   WHERE date BETWEEN :a AND :b GROUP BY 1"""), {"a": d1, "b": d2}):
        acc = out.setdefault(cid, [0, 0])
        acc[0] += int(shows or 0)
        acc[1] += int(clicks or 0)
    return out


def save(db: Session, month: date, by_creative: Dict[int, list]) -> int:
    """Апсерт снимка; меньшее прежнего не пишется (сырьё удаляется — снимок не должен «худеть»). Возвращает число строк."""
    if not by_creative:
        return 0
    meta = {r[0]: (r[1], r[2]) for r in db.execute(text(
        "SELECT id, placement_id, erid FROM ad_campaign_creative WHERE id = ANY(:i) AND placement_id IS NOT NULL"),
        {"i": list(by_creative)})}
    n = 0
    for cid, (shows, clicks) in by_creative.items():
        if cid not in meta or shows <= 0:
            continue
        pid, erid = meta[cid]
        db.execute(text("""
            INSERT INTO ord_erid_month_stat (month, placement_id, creative_id, erid, shows, clicks, captured_at)
            VALUES (:m, :p, :c, :e, :s, :k, now())
            ON CONFLICT ON CONSTRAINT uq_ord_erid_month_stat DO UPDATE
               SET shows = EXCLUDED.shows, clicks = EXCLUDED.clicks, erid = EXCLUDED.erid, captured_at = now()
             WHERE ord_erid_month_stat.shows <= EXCLUDED.shows"""),
            {"m": month, "p": pid, "c": cid, "e": erid, "s": shows, "k": clicks})
        n += 1
    return n


def capture(db: Session, month: date, csv_path: Optional[str] = None) -> int:
    from app.dsp.db import DspSessionLocal
    dsp_db = DspSessionLocal() if DspSessionLocal is not None else None
    try:
        n = save(db, month, collect(db, dsp_db, month, csv_path))
        db.commit()
        return n
    finally:
        if dsp_db is not None:
            dsp_db.close()


def _months(arg: Optional[str]) -> list:
    if arg:
        y, m = (int(x) for x in arg.split("-"))
        return [date(y, m, 1)]
    cur = datetime.now(MSK).date().replace(day=1)
    return [(cur - timedelta(days=1)).replace(day=1), cur]


def main() -> None:
    from app.database import SessionLocal
    p = argparse.ArgumentParser(description="Снимок разреза «площадка × креатив» для отчёта ОРД")
    p.add_argument("--month")
    p.add_argument("--csv")
    a = p.parse_args()
    db = SessionLocal()
    try:
        for m in _months(a.month):
            print(f"{m:%Y-%m}: строк снимка {capture(db, m, a.csv)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
