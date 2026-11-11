# -*- coding: utf-8 -*-
"""Ночной забор статистики Adfox через API (владелец 11.11.2026) — вместо ручного «↑ ADFOX» по ПОКАЗАМ.

Отчёт «По кампаниям» (v2, уровень owner) за день → строки как у ручного отчёта → тот же разбор (`traffic/adfox_import.resolve`,
ключ — название кампании `СДЕЛКА-ПЛОЩАДКА-crN-NN_ИНИЦИАЛЫ`). Показы API совпали с ручной загрузкой за 07.11 у всех 53 размещений.

Правила записи:
- только показы: клики API (commercial — 24 за день против 3 146 переходов ручного отчёта) и уникальных по кампаниям в API нет —
  владелец: «клики не трогать»; у существующей строки клики и уникальные остаются, у новой — 0 и пусто;
- пишется только однозначно сопоставленное; размещение, которое может стоять за несопоставленной строкой отчёта, за этот день
  не пишется (иначе сумма дня ляжет без части креативов);
- размещение с фактом DSP не пишется — задвоение (то же правило, что у ручной загрузки);
- окно — последние дни (`DAYS`): Adfox дописывает поздние показы, повтор перезаписывает показы дня.

    python -m app.adfox.stats            # вчера и два дня до него
    python -m app.adfox.stats --days 7
    python -m app.adfox.stats --dry      # показать, что запишется, не писать
"""
import app.model_registry  # noqa: F401  — крон отдельным процессом: внешние ключи должны находиться

import argparse
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.traffic import adfox_import as ai

log = logging.getLogger("finance.adfox")
MSK = timezone(timedelta(hours=3))
DAYS = 3
SKIP_UNRESOLVED = "в отчёте есть несопоставленная строка, которая может быть этим размещением"
SKIP_DSP = "размещение крутится в DSP — факт оттуда"


def to_rows(api_rows: Iterable[dict], day: date) -> List[dict]:
    """Строки API → строки ручного разбора. Клики не переносим (см. шапку), уникальных в API нет."""
    return [{"line": i, "day": day, "name": ai.clean_name(r.get("campaign_name")), "shows": int(r.get("impressions_commercial") or 0),
             "clicks": None, "uniques": None} for i, r in enumerate(api_rows, start=1)]


def select(rs: List[dict], dsp_placements: set) -> Tuple[Dict[tuple, dict], List[tuple]]:
    """Что писать: {(РК, размещение, день): {shows, creatives{креатив: показы}}} и пропущенные [(размещение, почему)]."""
    blocked = {(c.get("placement_id"), r["day"]) for r in rs if r.get("status") == ai.AMBIGUOUS for c in r.get("candidates") or []}
    agg: Dict[tuple, dict] = {}
    skipped: Dict[int, str] = {}
    for r in rs:
        if r.get("status") != ai.MATCHED:
            continue
        pl = r["placement_id"]
        if pl in dsp_placements:
            skipped[pl] = SKIP_DSP
            continue
        if (pl, r["day"]) in blocked:
            skipped[pl] = SKIP_UNRESOLVED
            continue
        a = agg.setdefault((r["campaign_id"], pl, r["day"]), {"shows": 0, "creatives": {}})
        a["shows"] += int(r["shows"] or 0)
        a["creatives"][r["creative_id"]] = a["creatives"].get(r["creative_id"], 0) + int(r["shows"] or 0)
    return agg, sorted(skipped.items())


def write(db: Session, agg: Dict[tuple, dict]) -> int:
    """Показы дня размещения и его креативов; клики и уникальные существующих строк не трогаются."""
    for (camp, pl, day), a in agg.items():
        db.execute(text("""
            INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, uniques, source, imported_at)
            VALUES (:c, :p, :d, :s, 0, NULL, :src, now())
            ON CONFLICT ON CONSTRAINT uq_ad_stat DO UPDATE SET shows = EXCLUDED.shows, imported_at = now()"""),
            {"c": camp, "p": pl, "d": day, "s": a["shows"], "src": ai.SOURCE})
        for cid, shows in (a.get("creatives") or {}).items():
            db.execute(text("""
                INSERT INTO adfox_creative_stat (creative_id, date, shows, clicks, uniques, imported_at)
                VALUES (:c, :d, :s, 0, NULL, now())
                ON CONFLICT ON CONSTRAINT uq_adfox_creative_day DO UPDATE SET shows = EXCLUDED.shows, imported_at = now()"""),
                {"c": cid, "d": day, "s": shows})
    return len(agg)


def _dsp_placements(db: Session, pls: list) -> set:
    return {r[0] for r in db.execute(text("""SELECT DISTINCT placement_id FROM ad_campaign_stat
                                              WHERE placement_id = ANY(:p) AND source IN ('dsp', 'ms')"""), {"p": pls or [0]})}


def sync_day(db: Session, cl, day: date, dry: bool = False) -> dict:
    rows = to_rows(cl.report_v2("campaigns", "owner", day.isoformat(), day.isoformat()), day)
    rs = ai.resolve(db, rows)
    pls = sorted({r["placement_id"] for r in rs if r.get("status") == ai.MATCHED})
    agg, skipped = select(rs, _dsp_placements(db, pls))
    n = 0 if dry else write(db, agg)
    return {"day": day.isoformat(), "rows": len(rows), "written": n, "would_write": len(agg), "skipped": skipped,
            "unmatched": [r["name"] for r in rs if r.get("status") == ai.UNMATCHED],
            "ambiguous": [r["name"] for r in rs if r.get("status") == ai.AMBIGUOUS],
            "shows": sum(a["shows"] for a in agg.values())}


def main() -> None:
    from app.adfox.client import AdfoxClient, AdfoxError
    from app.audit import log_action
    from app.database import SessionLocal
    p = argparse.ArgumentParser(description="Забор показов Adfox через API")
    p.add_argument("--days", type=int, default=DAYS)
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    today = datetime.now(MSK).date()
    db = SessionLocal()
    try:
        cl = AdfoxClient()
        for k in range(a.days, 0, -1):
            out = sync_day(db, cl, today - timedelta(days=k), a.dry)
            print(f"{out['day']}: строк {out['rows']}, записано размещений {out['written'] if not a.dry else out['would_write']} "
                  f"({out['shows']} показов), пропущено {len(out['skipped'])}, не сопоставлено {len(out['unmatched'])}, "
                  f"неоднозначно {len(out['ambiguous'])}")
            if not a.dry:
                db.commit()
                log_action(db, None, "adfox_api_sync", "ad_campaign", None,
                           f"Adfox API {out['day']}: показы записаны по {out['written']} размещениям ({out['shows']}); "
                           f"пропущено {len(out['skipped'])}, не сопоставлено {len(out['unmatched'])}")
    except AdfoxError as e:
        db.rollback()
        print(f"ОШИБКА: {e}")
        raise SystemExit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
