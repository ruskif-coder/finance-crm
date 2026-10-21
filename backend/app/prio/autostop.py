# -*- coding: utf-8 -*-
"""Автостоп площадки приоритезации по выполнению плана (владелец 19.10.2026: «останавливаем мы»).

Идёт после ночного сбора (`stats.__main__`): факт площадки — сумма ПОСЛЕДНИХ снимков по дням (`prio_stat_raw`; день дорастает
при перезаборе, снимки одного дня не складываются). Порог — цель площадки плюс её доля бонусного трафика сделки: бонус по
определению крутится сверх плана. Достигнут → «Стоп» в системе с перечиткой (`launch.toggle`), статус «остановлено»,
отметка `goal_reached_at`. Отметка стоит один раз: ручной «Старт» после автостопа — это докрутка, второй раз не стопим.
Сбор раз в сутки, поэтому перекрут до суток показов возможен — это известная цена варианта."""
import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.prio import models as M
from app.prio.client import PrioApiError
from app.prio.service import PrioError, plan_volume

log = logging.getLogger("finance.prio")


def facts(db: Session, camp_ids: list) -> dict:
    """camp_id → показы: по каждому дню последний снимок, по дням сумма."""
    if not camp_ids:
        return {}
    rows = db.execute(text("""
        SELECT camp_id, sum(shows) FROM (
            SELECT DISTINCT ON (camp_id, day) camp_id, shows FROM prio_stat_raw
             WHERE camp_id = ANY(:c) ORDER BY camp_id, day, pulled_at DESC, id DESC) t
         GROUP BY camp_id"""), {"c": camp_ids}).all()
    return {r[0]: int(r[1] or 0) for r in rows}


def bonus_ratio(db: Session, deal) -> float:
    """Бонус сделки как доля плана: площадка получает ту же долю сверх своей цели."""
    from app.final_recon import closing as CL
    mode, value = deal.bonus_traffic_mode, deal.bonus_traffic_value
    if not mode or not value:
        return 0.0
    plan = plan_volume(db, deal)
    if not plan:
        return 0.0
    base_net = CL.compute(db, deal)["base_plan_net"] if mode == "rub" else 0.0
    return CL.bonus_shows(mode, value, plan, base_net) / plan


def threshold(goal: int, ratio: float) -> int:
    return int(round(goal * (1 + ratio)))


def _candidates(db: Session) -> list:
    return (db.query(M.PrioPlacement)
            .filter(M.PrioPlacement.status == M.LIVE, M.PrioPlacement.camp_id.isnot(None),
                    M.PrioPlacement.goal_reached_at.is_(None), M.PrioPlacement.goal_imp > 0)
            .order_by(M.PrioPlacement.id).all())


def _deal_of(db: Session, p: M.PrioPlacement):
    from app.sales.models import SalesDeal
    did = db.execute(text("SELECT deal_id FROM prio_requests WHERE id = :r"), {"r": p.request_id}).scalar()
    return db.get(SalesDeal, did)


def _check_one(db: Session, client, p, got: dict, ratios: dict, L):
    """Одна площадка: None — до цели не дошла; item — остановлена (или `error`, если API не принял стоп)."""
    deal = _deal_of(db, p)
    if deal is None:
        return None
    if deal.id not in ratios:
        ratios[deal.id] = bonus_ratio(db, deal)
    fact, limit = got.get(p.camp_id, 0), threshold(int(p.goal_imp), ratios[deal.id])
    if fact < limit:
        return None
    item = {"id": p.id, "deal": deal.code, "deal_id": deal.id, "publisher_id": p.publisher_id, "fact": fact, "limit": limit}
    try:
        L.toggle(db, deal, p.id, False, client=client)
    except (PrioError, PrioApiError) as e:
        return {**item, "error": getattr(e, "message", str(e))}
    p.goal_reached_at = datetime.utcnow()
    db.flush()
    return item


def run(db: Session, client, *, commit: bool = True, notify: bool = None) -> dict:
    """Отказ API по одной площадке не останавливает остальные — она уходит в `failed` и повторится следующей ночью.
    Уведомления — после коммита (`notify` по умолчанию = `commit`: тест в откатываемой транзакции писем не шлёт)."""
    from app.prio import launch as L
    out = {"checked": 0, "stopped": [], "failed": []}
    pls = _candidates(db)
    got = facts(db, [p.camp_id for p in pls])
    ratios: dict = {}
    for p in pls:
        out["checked"] += 1
        try:
            with db.begin_nested():                       # сбой одной площадки (нет сделки, сверка упала) не роняет прогон (аудит 20.10)
                item = _check_one(db, client, p, got, ratios, L)
        except Exception as e:  # noqa: BLE001
            log.exception("автостоп: площадка запроса %s не проверена", p.id)
            out["failed"].append({"id": p.id, "deal": None, "deal_id": None, "publisher_id": p.publisher_id, "error": str(e)[:200]})
            continue
        if item is None:
            continue
        (out["failed"] if item.get("error") else out["stopped"]).append(item)
        if commit and not item.get("error"):
            db.commit()                                     # остановленная в API — сразу в базе, метка не теряется при сбое дальше
    if commit:
        db.commit()
    if commit if notify is None else notify:
        tell(db, out)
    return out


def tell(db: Session, out: dict) -> None:
    from app.notify import prio as N
    from app.sales.models import SalesDeal
    for x in out["stopped"]:
        deal = db.get(SalesDeal, x["deal_id"])
        N.goal_reached(db, deal, x)
        N.live_to_site(db, deal, db.get(M.PrioPlacement, x["id"]), False, "план показов выполнен")
    for x in out["failed"]:
        if x.get("deal_id"):
            N.stop_failed(db, db.get(SalesDeal, x["deal_id"]), x)
    db.commit()


def report(o: dict) -> str:
    parts = [f"Автостоп приоритезации: проверено {o['checked']}, остановлено {len(o['stopped'])}"]
    parts += [f"{x['deal']} площадка {x['publisher_id']}: {x['fact']} из {x['limit']} — стоп" for x in o["stopped"]]
    parts += [f"{x['deal']} площадка {x['publisher_id']}: стоп не прошёл — {x['error']}" for x in o["failed"]]
    return "; ".join(parts)
