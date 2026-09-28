"""Открутка РК по сделкам — пачкой, для очереди аккаунта и для срочности.

Ничего не считает заново: факт, площадки и статусы берутся теми же функциями, что
кормят дашборд трафика и блок «Рекламная кампания» карточки (`sales_dashboard.deal_campaign`),
флайт — `ad/flight.progress`. Отличие одно: там РК одна, здесь — все РК очереди разом,
иначе строка на сделку стоила бы пять запросов.
"""
from datetime import date
from typing import Dict, Iterable

from sqlalchemy.orm import Session


def closed_pace(fc: dict):
    """Доля флайта по ЗАКРЫТЫМ дням — с чем сравнивать факт для отставания.

    `flight.progress` считает сегодняшний день отработанным (`done` включает сегодня), а
    статистика — дневной срез, и за сегодня её ещё нет. Сравнение факта с `pace` делало
    РК точно по плану «отстающей» на 1/done: на пятый день 30-дневного флайта — на 20 %
    (ревью 28.09.2026). Флайт кончился — 1; не начался или идёт первый день — 0."""
    total, done = fc.get("days_total"), fc.get("days_done")
    if not total or done is None:
        return None
    if fc.get("flight_over"):
        return 1.0
    return max(0, done - 1) / total


def campaigns_by_deal(db: Session, deal_ids: Iterable[int]) -> Dict[int, object]:
    """Последняя по месяцу РК каждой сделки — тем же порядком, что `stage_checks.Ctx.campaign`."""
    from app.ad.models import AdCampaign
    ids = list(deal_ids)
    if not ids:
        return {}
    out: dict = {}
    for c in (db.query(AdCampaign).filter(AdCampaign.deal_id.in_(ids))
              .order_by(AdCampaign.deal_id, AdCampaign.month.desc().nullslast(),
                        AdCampaign.id.desc()).all()):
        out.setdefault(c.deal_id, c)
    return out


def delivery_by_deal(db: Session, campaigns: Dict[int, object], today: date) -> Dict[int, dict]:
    """{сделка: открутка} для сделок, у которых есть РК.

    Ключи — как у `flight.progress` плюс факт, план и площадки «крутится / всего».
    Без статистики `fact_shows` = None и `done_pct` = None: «ещё не пришло», а не «ноль»."""
    from app.ad.flight import (PLACEMENT_RUNNING, as_placement_scale, best_chain_status,
                               effective_status, progress)
    from app.routers import traffic_dashboard as td

    cids = [c.id for c in campaigns.values()]
    if not cids:
        return {}
    facts = td._facts(db, cids)
    pls = td._placements_of(db, cids)
    creatives = td._creatives_all(db, cids)

    out = {}
    for deal_id, c in campaigns.items():
        fact = (facts.get(c.id) or {}).get("shows")
        mine = creatives.get(c.id, {})
        statuses = [effective_status(p["status"], best_chain_status(
            as_placement_scale(x) for x in mine.get(p["id"], [])))
            for p in pls.get(c.id, [])]
        out[deal_id] = {
            "campaign_id": c.id,
            "plan_show": c.plan_show, "plan_budget": c.plan_budget, "fact_shows": fact,
            "placements": len(statuses),
            "placements_on": sum(1 for s in statuses if s in PLACEMENT_RUNNING),
            **progress(c.plan_show, fact, c.date_start, c.date_end, today),
        }
        out[deal_id]["closed_pace"] = closed_pace(out[deal_id])
    return out
