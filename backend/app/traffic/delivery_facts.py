# -*- coding: utf-8 -*-
"""Выборки статистики, площадок и креативов по списку РК.

Вынесено из `routers/traffic_dashboard.py` 07.10.2026: ими считает открутку `sales/deal_delivery.py` (а через него крон
`notify/scanner.py`), слой HTTP там не нужен. Роутер реэкспортирует имена.
"""
from typing import List
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.ad import build
from app.ad.stat_sources import fact_sources


def _facts(db: Session, campaign_ids: List[int]) -> dict:
    if not campaign_ids:
        return {}
    rows = db.execute(text(
        "SELECT campaign_id, sum(shows) AS shows, sum(clicks) AS clicks "
        "FROM ad_campaign_stat WHERE campaign_id = ANY(:i) AND source = ANY(:src) "
        "GROUP BY campaign_id"),
        {"i": campaign_ids, "src": fact_sources()}).mappings().all()
    return {r["campaign_id"]: dict(r) for r in rows}

def _creatives_all(db: Session, campaign_ids: List[int]) -> dict:
    """Креативы НЕСКОЛЬКИХ РК: {campaign_id: {placement_id: [статусы]}}.

    Дашборд считает статус каждой РК из её креативов, и запрос на каждую превратил бы
    один экран в шестьдесят обращений — тот же приём, что `page_ids` в реестре сделок.
    """
    if not campaign_ids:
        return {}
    rows = db.execute(text(
        "SELECT campaign_id, placement_id, status FROM ad_campaign_creative "
        "WHERE campaign_id = ANY(:i)"), {"i": campaign_ids}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["campaign_id"], {}).setdefault(r["placement_id"], []).append(r["status"])
    return out

def _placements_of(db: Session, campaign_ids: List[int]) -> dict:
    """Площадки всех видимых РК одним запросом — для долей, виновников и счётчиков.

    Раскрывать каждую РК ради этого нельзя: виджет «площадки-виновники» отвечает на
    вопрос «кто тянет вниз ВЕСЬ портфель», и по одной РК он не собирается вовсе.
    """
    if not campaign_ids:
        return {}
    rows = db.execute(text("""
        SELECT p.campaign_id, p.id, p.publisher_id, p.status, p.weight,
               p.plan_show AS plan_stored, p.share AS share_stored,
               pub.code, pub.domain, pub.name AS publisher,
               (SELECT sum(s.shows) FROM ad_campaign_stat s
                 WHERE s.placement_id = p.id AND s.source = ANY(:src)) AS fact,
               """ + build.PLACEMENT_FIXED_SQL + """ AS fixed
          FROM ad_campaign_placement p
          JOIN sales_publishers pub ON pub.id = p.publisher_id
         WHERE p.campaign_id = ANY(:i)
    """), {"i": campaign_ids, "src": fact_sources()}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["campaign_id"], []).append(dict(r))
    return out
