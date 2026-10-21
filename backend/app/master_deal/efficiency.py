# -*- coding: utf-8 -*-
"""Эффективность мастер-сделки — предварительный расчёт по пакету (владелец 19.10.2026).

Числа сделки берутся у итоговой сверки (`final_recon.closing.compute`): сумма ДС до НДС, СК и себестоимость там уже посчитаны,
второго расчёта нет. Правила:
- выручка — сумма ДС до НДС; при «скидке в счёт» СК из неё уже вычтена и второй раз не вычитается;
- СК «постоплата» — наш будущий расход: вычитается из прибыли;
- себестоимость — введённая аккаунтом на сверке; нет её — оценка по факту показов × CPM договора площадки (`cpm_contract`),
  с долей показов, у которых CPM известен; нет и оценки — неизвестна;
- прибыль и маржа пакета — только если себестоимость известна у всех сделок. Иначе «нет данных», а не ноль: ноль выглядел бы
  как стопроцентная маржа."""
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

POSTPAY = "постоплата"


def _r2(v) -> float:
    return round(float(v or 0) + 1e-9, 2)


def estimate_from(stats: List[tuple]) -> Optional[dict]:
    """[(показы, CPM площадки | None)] → {cost, coverage_pct} или None, если показов нет."""
    shows = sum(s for s, _ in stats)
    if not shows:
        return None
    priced = [(s, c) for s, c in stats if c is not None]
    return {"cost": _r2(sum(s * c / 1000.0 for s, c in priced)),
            "coverage_pct": round(sum(s for s, _ in priced) / shows * 100, 1)}


def estimate(db: Session, deal_id: int) -> Optional[dict]:
    """Оценка себестоимости сделки: фактические показы её РК по площадкам × CPM договора площадки."""
    from app.ad.stat_sources import fact_sources
    rows = db.execute(text("""
        SELECT sum(s.shows), max(pb.cpm_contract)
          FROM ad_campaign_stat s JOIN ad_campaign a ON a.id = s.campaign_id
          LEFT JOIN ad_campaign_placement p ON p.id = s.placement_id
          LEFT JOIN sales_publishers pb ON pb.id = p.publisher_id
         WHERE a.deal_id = :d AND s.source = ANY(:src)
         GROUP BY s.placement_id"""), {"d": deal_id, "src": fact_sources()}).all()
    return estimate_from([(int(r[0] or 0), float(r[1]) if r[1] is not None else None) for r in rows])


def row(code: str, st: dict, est: Optional[dict]) -> dict:
    revenue = _r2(st.get("total_net"))
    sk = st.get("sk") or {}
    sk_cost = _r2(sk.get("amount_net")) if sk.get("mode") == POSTPAY else 0.0
    if st.get("cost_net") is not None:
        cost, src, cov = _r2(st["cost_net"]), "введена", None
    elif est is not None:
        cost, src, cov = _r2(est["cost"]), "оценка", est["coverage_pct"]
    else:
        cost, src, cov = None, None, None
    profit = _r2(revenue - sk_cost - cost) if cost is not None else None
    return {"code": code, "revenue": revenue, "sk_mode": sk.get("mode"), "sk_percent": sk.get("percent"),
            "sk_amount": _r2(sk.get("amount_net")), "sk_cost": sk_cost, "cost": cost, "cost_source": src,
            "coverage_pct": cov, "profit": profit,
            "margin_pct": round(profit / revenue * 100, 1) if (profit is not None and revenue) else None}


def total(rows: List[dict]) -> dict:
    revenue = _r2(sum(r["revenue"] for r in rows))
    missing = [r["code"] for r in rows if r["cost"] is None]
    cost = _r2(sum(r["cost"] or 0 for r in rows))
    sk_cost = _r2(sum(r["sk_cost"] for r in rows))
    profit = _r2(revenue - sk_cost - cost) if not missing else None
    return {"revenue": revenue, "sk_cost": sk_cost, "sk_amount": _r2(sum(r["sk_amount"] for r in rows)), "cost": cost,
            "profit": profit, "margin_pct": round(profit / revenue * 100, 1) if (profit is not None and revenue) else None,
            "missing_cost": missing, "estimated": [r["code"] for r in rows if r["cost_source"] == "оценка"]}


def of_master(db: Session, deals: list) -> dict:
    from app.final_recon import closing as CL
    rows = [row(d.code, CL.compute(db, d), estimate(db, d.id)) for d in deals]
    return {"rows": rows, "total": total(rows)}
