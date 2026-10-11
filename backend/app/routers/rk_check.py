# -*- coding: utf-8 -*-
"""Экран «Трафики → Проверка РК» (владелец 11.10.2026). Своё право `traffic_check`:
view — экран, edit — «перепроверить сейчас». Расчёт — app/ad/rk_check.py."""
from datetime import timedelta
from typing import Dict, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import retention
from app.ad import rk_check as R
from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("traffic_check", "view")
EDIT = require_permission("traffic_check", "edit")
SUMMARY_VIEW = require_permission("traffic_dashboard", "view")

MAX_DAYS = 92
_LEVEL_ORDER = {R.RED: 0, R.YELLOW: 1, R.GREEN: 2, R.SKIP: 3}


def since_of(history: List[tuple], level: str) -> str:
    """С какого дня непрерывно держится уровень. `history` — [(дата, уровень)] по возрастанию.
    Считаем назад от последнего дня, пока уровень тот же; пропущенный день прерывает серию."""
    if not history:
        return None
    start, prev = history[-1][0], history[-1][0]
    for d, lv in reversed(history[:-1]):
        if lv != level or (prev - d).days != 1:
            break
        start, prev = d, d
    return str(start)


def _latest_day(db: Session):
    return db.execute(text("SELECT max(run_date) FROM rk_check_result")).scalar()


@router.get("")
def overview(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    day = _latest_day(db)
    if day is None:
        return {"run_date": None, "summary": {}, "groups": [{"key": k, "title": t} for k, t in R.GROUPS],
                "campaigns": []}
    rows = db.execute(text("""SELECT r.campaign_id, r.placement_id, r.check_key, r.level, r.value, r.message,
                                     d.code, d.title, c.status, c.date_start, c.date_end,
                                     coalesce(pb.domain, pb.name) AS pname
                                FROM rk_check_result r
                                JOIN ad_campaign c ON c.id = r.campaign_id JOIN sales_deals d ON d.id = c.deal_id
                                LEFT JOIN ad_campaign_placement p ON p.id = r.placement_id
                                LEFT JOIN sales_publishers pb ON pb.id = p.publisher_id
                               WHERE r.run_date = :d ORDER BY r.campaign_id, r.id"""), {"d": day}).mappings().all()
    since_from = day - timedelta(days=MAX_DAYS)
    hist: Dict[tuple, list] = {}
    for r in db.execute(text("""SELECT campaign_id, check_key, run_date, level FROM rk_check_result
                                 WHERE placement_id IS NULL AND run_date BETWEEN :a AND :b
                                 ORDER BY run_date"""), {"a": since_from, "b": day}).all():
        hist.setdefault((r[0], r[1]), []).append((r[2], r[3]))
    camps: Dict[int, dict] = {}
    for r in rows:
        c = camps.setdefault(r["campaign_id"], {
            "id": r["campaign_id"], "code": r["code"], "title": r["title"], "status": r["status"],
            "date_start": r["date_start"], "date_end": r["date_end"], "checks": {}, "groups": {}})
        key = r["check_key"]
        if r["placement_id"] is None:
            grp, title = R.CHECKS[key]
            c["checks"][key] = {"key": key, "group": grp, "title": title, "level": r["level"], "message": r["message"],
                                "value": r["value"], "placements": [],
                                "since": since_of(hist.get((r["campaign_id"], key), []), r["level"])
                                if r["level"] in (R.RED, R.YELLOW) else None}
        elif key in c["checks"]:
            c["checks"][key]["placements"].append({"placement_id": r["placement_id"], "name": r["pname"],
                                                   "level": r["level"], "message": r["message"], "value": r["value"]})
    common = R.common_keys({cid: {k: v["level"] for k, v in c["checks"].items()} for cid, c in camps.items()})
    out = []
    for c in camps.values():
        # Общая причина (встал съём, не загружен Adfox у многих РК) — приглушена и уровень РК не поднимает.
        for k, v in c["checks"].items():
            v["common"] = k in common
        own = {k: v for k, v in c["checks"].items() if k not in common}
        c["groups"] = R.group_levels({k: R.Result(v["level"], "") for k, v in own.items()})
        c["worst"] = R._worst([v["level"] for v in own.values()])
        c["checks"] = sorted(c["checks"].values(), key=lambda x: (_LEVEL_ORDER[x["level"]], list(R.CHECKS).index(x["key"])))
        out.append(c)
    out.sort(key=lambda c: (_LEVEL_ORDER[c["worst"]], -sum(1 for x in c["checks"] if x["level"] == R.RED), c["code"]))
    summary = {lv: sum(1 for c in out if c["worst"] == lv) for lv in (R.RED, R.YELLOW, R.GREEN, R.SKIP)}
    return {"run_date": str(day), "summary": summary, "keep_months": retention.JOURNAL_MONTHS,
            "common": [{"key": k, "title": R.CHECKS[k][1], "campaigns": n} for k, n in common.items()],
            "groups": [{"key": k, "title": t} for k, t in R.GROUPS], "campaigns": out}


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(SUMMARY_VIEW)):
    """Сводка по всем РК для дашборда трафика (читает записанный ночной прогон). Право — дашборда."""
    day = _latest_day(db)
    if day is None:
        return {"run_date": None, "checked_at": None, "need_action": 0, "common": [], "by_campaign": {}}
    rows = db.execute(text("""SELECT r.campaign_id, d.code, r.check_key, r.level, r.message, r.created_at
                                FROM rk_check_result r JOIN ad_campaign c ON c.id = r.campaign_id
                                JOIN sales_deals d ON d.id = c.deal_id
                               WHERE r.run_date = :d AND r.placement_id IS NULL"""), {"d": day}).all()
    by: Dict[int, dict] = {}
    stamp = None
    for cid, code, key, lv, msg, created in rows:
        by.setdefault(cid, {"code": code, "checks": []})["checks"].append({"key": key, "level": lv, "message": msg})
        stamp = created if stamp is None or created > stamp else stamp
    common = R.common_keys({cid: {x["key"]: x["level"] for x in v["checks"]} for cid, v in by.items()})
    out = {}
    for cid, v in by.items():
        sm = R.build_summary(v["checks"], common)
        out[str(cid)] = {"code": v["code"], **sm}
    return {"run_date": str(day),
            "checked_at": stamp.astimezone(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%dT%H:%M") if stamp else None,
            "need_action": sum(1 for v in out.values() if v["worst"] == R.RED),
            "common": [{"key": k, "title": R.CHECKS[k][1], "campaigns": n} for k, n in common.items()],
            "by_campaign": out}


@router.post("/run")
def run_now(db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Перепроверить все идущие РК сейчас (перезаписывает сегодняшние строки)."""
    out = R.save(db, R.load(db), R.today_msk())
    log_action(db, user, "rk_check_run", "rk_check", None,
               f"РК: {out['campaigns']}, красных проверок: {out['levels'][R.RED]}, жёлтых: {out['levels'][R.YELLOW]}")
    return out


@router.get("/{campaign_id}/history")
def history(campaign_id: int, days: int = 30, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    if not 1 <= days <= MAX_DAYS:
        raise HTTPException(400, f"Окно — от 1 до {MAX_DAYS} дней")
    if db.execute(text("SELECT 1 FROM ad_campaign WHERE id = :c"), {"c": campaign_id}).first() is None:
        raise HTTPException(404, "РК не найдена")
    since = R.today_msk() - timedelta(days=days)
    rows = db.execute(text("""SELECT check_key, run_date, level, message FROM rk_check_result
                               WHERE campaign_id = :c AND placement_id IS NULL AND run_date >= :s
                               ORDER BY run_date"""), {"c": campaign_id, "s": since}).all()
    by: Dict[str, list] = {}
    for key, d, lv, msg in rows:
        by.setdefault(key, []).append({"date": str(d), "level": lv, "message": msg})
    return {"campaign_id": campaign_id, "days": days,
            "checks": [{"key": k, "title": R.CHECKS[k][1], "group": R.CHECKS[k][0], "days": by.get(k, [])}
                       for k in R.CHECKS]}
