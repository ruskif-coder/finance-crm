# -*- coding: utf-8 -*-
"""«Трафики → Биддер» (владелец 05.10.2026): правила раскладки объёма, раскладка РК.

Расчёт — не здесь: правила в `app/bidder/rules`, раскладка — `build.campaign_layout`, та
же, что у ночного пересчёта (`app/ad/daily_shares`). Страница объясняет ровно то число,
которое уходит в DSP. Право своё (`bidder`), без бэкфилла: пока только владелец.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad import balance, build
from app.ad.flight import HOLD_DAYS, PLACEMENT_RUNNING
from app.ad.models import AdCampaign
from app.ad.stat_sources import fact_as_of, is_stale
from app.bidder.facts import placement_facts
from app.bidder.rules import RULES, explain
from app.database import get_db
from app.models import User
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("bidder", "view")

CRON = "ежедневно в 02:00 UTC (05:00 МСК), после сбора статистики DSP в 01:30 UTC"


@router.get("")
def overview(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    as_of = fact_as_of(db)
    cap = balance.share_cap(db)
    return {"rules": RULES, "cron": CRON, "hold_days": HOLD_DAYS,
            "cap_pct": round(cap * 100, 1) if cap else None,
            "fact_as_of": as_of.isoformat(), "stale": is_stale(as_of)}


@router.get("/runs")
def runs(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Журнал ночных прогонов, новые сверху."""
    from app.bidder import journal
    return journal.runs(db)


@router.get("/runs/{run_id}")
def run_changes(run_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Что поменялось у площадок в прогоне + разбор по причинам и проверки прогона."""
    from app.bidder import checks as K
    from app.bidder import journal
    from app.bidder.rules import REASONS
    run = journal.run(db, run_id)
    if run is None:
        raise HTTPException(404, "Прогон не найден")
    changes = journal.changes_of(db, run_id)
    ids = sorted({c["campaign_id"] for c in changes})
    starts = dict(db.execute(text("SELECT id, date_start FROM ad_campaign WHERE id = ANY(:i)"),
                             {"i": ids}).all()) if ids else {}
    return {"summary": K.summarize(changes, starts, run["run_day_msk"]),
            "checks": run.get("checks") or [],
            "changes": [{**c, "reason_label": REASONS.get(c["reason"], c["reason"])}
                        for c in changes]}


@router.get("/campaigns")
def campaigns(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Незавершённые РК с планом — для выбора на странице. `running` — сколько площадок
    крутит прямо сейчас (`flight.PLACEMENT_RUNNING`): «запущена» на странице = крутится
    хотя бы одна, а не сохранённый статус РК, который бывает расчётным."""
    rows = db.execute(text(
        "SELECT c.id, d.code, d.title, c.plan_show, c.date_start, c.date_end, c.status, "
        "(SELECT count(*) FROM ad_campaign_placement p WHERE p.campaign_id = c.id "
        " AND p.status = ANY(:run)) AS running "
        "FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id "
        "WHERE c.plan_show > 0 AND (c.status IS NULL OR c.status <> ALL(:closed)) "
        "ORDER BY c.date_start DESC NULLS LAST, c.id DESC"),
        {"closed": list(build.CAMPAIGN_CLOSED),
         "run": list(PLACEMENT_RUNNING)}).mappings().all()
    return [{**r, "date_start": r["date_start"] and r["date_start"].isoformat(),
             "date_end": r["date_end"] and r["date_end"].isoformat()} for r in rows]


@router.get("/layout/{campaign_id}")
def layout(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Раскладка РК: план = заданные + выбывшие по факту + по весам, у площадки — почему."""
    camp = db.query(AdCampaign).filter(AdCampaign.id == campaign_id).first()
    if camp is None:
        raise HTTPException(404, "РК не найдена")
    got = placement_facts(db, [campaign_id])
    facts = got.get(campaign_id) if got is not None else None
    # Факт для показа — всегда, даже когда раскладка его не учла (срез устарел).
    shown = facts if facts is not None else _facts_any(db, campaign_id)
    pls, out = build.campaign_layout(db, campaign_id, facts=facts, facts_given=True)
    # Записанный ночью план — то, что стоит лимитами в DSP (владелец 05.10.2026: экраны
    # показывают записанный). Расчёт по правилам сейчас — рядом, если разошёлся.
    stored = {p.id: p.plan_show for p in pls}
    stored_share = {p.id: p.share for p in pls}
    names = dict(db.execute(text(
        "SELECT p.id, coalesce(sp.domain, sp.name) FROM ad_campaign_placement p "
        "JOIN sales_publishers sp ON sp.id = p.publisher_id WHERE p.campaign_id = :c"),
        {"c": campaign_id}).all())
    cap = out.get("cap")
    cap_abs = cap * camp.plan_show if (cap and camp.plan_show) else None
    rows, totals = [], {"fixed": 0, "settled": 0, "by_weight": 0}
    for r in out["rows"]:
        fact = shown.get(r["id"], 0)
        why = explain(r, fact, out["facts_used"], cap_abs)
        n = r["plan_show"] or 0
        totals["fixed" if why["code"] == "fixed" else
               "settled" if why["code"] == "settled" else "by_weight"] += n
        st = stored.get(r["id"])
        rows.append({"id": r["id"], "site": names.get(r["id"]), "status": r["status"],
                     # доля — тоже записанная, к плану в DSP (ревью 05.10.2026)
                     "weight": r.get("weight"), "share": stored_share.get(r["id"]) or 0,
                     "plan_stored": round(st) if st else None, "plan_show": r["plan_show"],
                     "changes_tonight": (round(st) if st else None) != r["plan_show"],
                     "fact": fact, "reason": why["code"], "reason_label": why["label"]})
    rows.sort(key=lambda x: -(x["plan_stored"] or x["plan_show"] or 0))
    return {"campaign_id": campaign_id, "plan_show": camp.plan_show,
            "date_start": camp.date_start and camp.date_start.isoformat(),
            "date_end": camp.date_end and camp.date_end.isoformat(),
            "facts_used": out["facts_used"], "cap_pct": round(cap * 100, 1) if cap else None,
            "totals": totals, "rows": rows,
            # Факт уже больше плана РК: «не ниже факта» даёт сумму сверх плана — перекрут.
            "over": max(0, sum(totals.values()) - round(camp.plan_show or 0))}


def _facts_any(db: Session, campaign_id: int) -> dict:
    from app.ad.stat_sources import fact_sources
    return {pid: int(n or 0) for pid, n in db.execute(text(
        "SELECT placement_id, sum(shows) FROM ad_campaign_stat WHERE campaign_id = :c "
        "AND placement_id IS NOT NULL AND source = ANY(:s) GROUP BY placement_id"),
        {"c": campaign_id, "s": fact_sources()}).all()}
