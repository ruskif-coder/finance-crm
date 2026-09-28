"""Цена единицы и план/факт закупленной метрики — для реестра сделок (владелец 28.09.2026).

Две колонки реестра:

* **цена единицы** — `unit_price` строк медиаплана (CPM — за тысячу показов, CPC — за
  клик, Фикс — за штуку), вместе с моделью. Одна цена на все строки — она; разные —
  диапазоном «мин–макс»: выбирать одну молча значило бы показать цену, которой в плане
  у части объёма нет;
* **план / факт** — той метрики, которая закуплена: показы у CPM, клики у CPC. У Фикса
  и пакетов закупаются штуки, а не показы, — колонка пустая («если есть»).

План — объём строк медиаплана этой модели (у CPM объём = показы, у CPC = клики, см.
`mp_row`). Медиаплан — тот же, что даёт сумму сделки: старшая версия каждой группы, план
со строками (`mp_amounts`). Факт — наш счётчик по РК сделки (`stat_sources.OWN`), без
верификатора.

Несколько моделей в одном плане (бывает CPM + CPC) — метрикой берётся модель с бОльшим
бюджетом, а в ответе остаётся признак `mixed`, чтобы экран не выдавал часть плана за весь.
"""
from typing import Dict, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad.stat_sources import fact_sources
from app.sales import mp_row

METRIC_OF = {"CPM": "shows", "CPC": "clicks"}


def _model(m) -> str:
    m = (m or "").strip().upper()
    return {"FIX": "Fix", "ФИКС": "Fix", "ПАКЕТ": "Пакет"}.get(m, m or "—")


def _latest_rows(db: Session, ids) -> Dict[int, list]:
    """Строки последних версий МП по сделке — то же правило, что у суммы сделки."""
    rows = db.execute(text("""
        WITH latest AS (
            SELECT DISTINCT ON (p.deal_id, p.group_id) p.id, p.deal_id
              FROM sales_media_plans p
             WHERE p.deal_id = ANY(:ids)
               AND EXISTS (SELECT 1 FROM sales_media_plan_rows r WHERE r.plan_id = p.id)
             ORDER BY p.deal_id, p.group_id, p.version DESC
        )
        SELECT l.deal_id, r.model, r.volume, r.unit_price, r.discount
          FROM latest l JOIN sales_media_plan_rows r ON r.plan_id = l.id
    """), {"ids": ids}).mappings().all()
    out: Dict[int, list] = {}
    for r in rows:
        out.setdefault(r["deal_id"], []).append(r)
    return out


def _facts(db: Session, ids) -> Dict[int, dict]:
    rows = db.execute(text("""
        SELECT c.deal_id, sum(s.shows) AS shows, sum(s.clicks) AS clicks
          FROM ad_campaign c JOIN ad_campaign_stat s ON s.campaign_id = c.id
         WHERE c.deal_id = ANY(:ids) AND s.source = ANY(:src)
         GROUP BY c.deal_id
    """), {"ids": ids, "src": fact_sources()}).mappings().all()
    return {r["deal_id"]: {"shows": int(r["shows"] or 0), "clicks": int(r["clicks"] or 0)}
            for r in rows}


def summarize(rows, fact=None) -> dict:
    """Строки одной сделки → поля двух колонок. Без базы — проверяется комбинациями."""
    by_model: Dict[str, dict] = {}
    for r in rows:
        m = _model(r["model"])
        a = by_model.setdefault(m, {"budget": 0.0, "volume": 0.0, "prices": set()})
        a["budget"] += mp_row.row_net(r["model"], r["volume"], r["unit_price"], r["discount"] or 0)
        a["volume"] += mp_row.num(r["volume"])
        if r["unit_price"] not in (None, ""):
            a["prices"].add(round(mp_row.num(r["unit_price"]), 2))
    if not by_model:
        return {}
    main = max(by_model, key=lambda k: (by_model[k]["budget"], k))
    a = by_model[main]
    prices = sorted(a["prices"])
    metric = METRIC_OF.get(main)
    out = {"model": main,
           "price_min": prices[0] if prices else None,
           "price_max": prices[-1] if prices else None,
           "mixed": len(by_model) > 1,
           "metric": metric, "plan": None, "fact": None}
    if metric:
        out["plan"] = round(a["volume"])
        out["fact"] = (fact or {}).get(metric)
    return out


def load(db: Session, deal_ids: Iterable[int]) -> Dict[int, dict]:
    """{сделка: поля колонок} для страницы реестра — два запроса на всю страницу."""
    ids = [i for i in deal_ids if i is not None]
    if not ids:
        return {}
    rows, facts = _latest_rows(db, ids), _facts(db, ids)
    return {d: summarize(rs, facts.get(d)) for d, rs in rows.items()}
