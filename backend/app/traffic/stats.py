# -*- coding: utf-8 -*-
"""«Трафики → Статистика» (владелец 03.10.2026): по текущим РК накопительно — общая стата,
«кукуха» и база (= общая − «кукуха»).

«Кукуха» — блок по умолчанию площадки в нашей DSP; по кампаниям DSP его не делит. Поэтому
сутки блока площадки (`dsp_block_stat`) делятся между РК по их суточным показам DSP на
этой площадке:

    кукуха(РК, площадка, день) = кукуха(площадка, день) × DSP(РК, пл., день) / DSP(все РК, пл., день)

Знаменатель — ВСЕ РК площадки за день, а не только текущие: иначе доля текущих была бы
завышена. Отчёт Adfox «кукухи» не содержит (это блок нашей DSP): у Adfox база = общая.
Факт системы не трогается — «база» считается только для показа.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad.stat_sources import OWN

ADFOX = "adfox"


def current_campaigns(db: Session, allowed: Optional[set] = None,
                      period: Optional[str] = None) -> Dict[int, dict]:
    """РК для экрана. Без периода — текущие: запущены или сегодня внутри флайта. С периодом
    `ГГГГ-ММ` — РК сделок этого финансового месяца (период сделки, а не даты РК: так
    отбирают сделки по всей системе)."""
    if period:
        where = """d.period_from <= (CAST(:m AS date) + INTERVAL '1 month' - INTERVAL '1 day')
                   AND coalesce(d.period_to, d.period_from) >= CAST(:m AS date)"""
        args = {"m": f"{period}-01"}
    else:
        where = """c.status = 'запущена'
                OR (c.date_start <= current_date AND coalesce(c.date_end, current_date) >= current_date)"""
        args = {}
    rows = db.execute(text(f"""
        SELECT c.id, c.status, c.date_start, c.date_end, c.plan_show, d.code AS deal, d.id AS deal_id
          FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
         WHERE {where}"""), args).mappings().all()
    return {r["id"]: dict(r) for r in rows if allowed is None or r["id"] in allowed}


def months(db: Session) -> List[str]:
    """Месяцы, в которых есть сделки с РК, — для переключателя периода, новые сверху."""
    return [r[0] for r in db.execute(text("""
        SELECT DISTINCT to_char(d.period_from, 'YYYY-MM') FROM ad_campaign c
          JOIN sales_deals d ON d.id = c.deal_id
         WHERE d.period_from IS NOT NULL ORDER BY 1 DESC""")).all()]


def _fact(db: Session, campaign_ids) -> List[dict]:
    """Факт по (РК, площадка, день, Adfox ли) — наш счётчик целиком (`OWN`)."""
    return [dict(r) for r in db.execute(text("""
        SELECT s.campaign_id, pl.publisher_id, s.date, (s.source = :adfox) AS adfox,
               sum(s.shows) AS shows
          FROM ad_campaign_stat s
          LEFT JOIN ad_campaign_placement pl ON pl.id = s.placement_id
         WHERE s.campaign_id = ANY(:c) AND s.source = ANY(:own)
         GROUP BY 1, 2, 3, 4"""),
        {"c": list(campaign_ids), "own": list(OWN), "adfox": ADFOX}).mappings()]


def _dsp_totals(db: Session, pub_days) -> Dict[tuple, int]:
    """Показы DSP ВСЕХ РК на площадке за день — знаменатель доли."""
    pubs = sorted({p for p, _ in pub_days if p})
    days = sorted({d for _, d in pub_days})
    if not pubs or not days:
        return {}
    return {(r[0], r[1]): int(r[2]) for r in db.execute(text("""
        SELECT pl.publisher_id, s.date, sum(s.shows)
          FROM ad_campaign_stat s JOIN ad_campaign_placement pl ON pl.id = s.placement_id
         WHERE pl.publisher_id = ANY(:p) AND s.date = ANY(:d)
           AND s.source = ANY(:own) AND s.source <> :adfox
         GROUP BY 1, 2"""), {"p": pubs, "d": days, "own": list(OWN), "adfox": ADFOX})}


def _kukuha(db: Session, pub_days) -> Dict[tuple, int]:
    pubs = sorted({p for p, _ in pub_days if p})
    days = sorted({d for _, d in pub_days})
    if not pubs or not days:
        return {}
    return {(r[0], r[1]): int(r[2]) for r in db.execute(text("""
        SELECT publisher_id, date, sum(shows) FROM dsp_block_stat
         WHERE publisher_id = ANY(:p) AND date = ANY(:d) GROUP BY 1, 2"""),
        {"p": pubs, "d": days})}


def compute(db: Session, allowed: Optional[set] = None, period: Optional[str] = None) -> dict:
    """Строки «РК × площадка» накопительно + когда последний раз снята «кукуха»."""
    camps = current_campaigns(db, allowed, period)
    fact = _fact(db, camps) if camps else []
    dsp_cells = {(f["publisher_id"], f["date"]) for f in fact if not f["adfox"]}
    totals = _dsp_totals(db, dsp_cells)
    kuk = _kukuha(db, dsp_cells)

    acc: Dict[tuple, dict] = defaultdict(lambda: {"dsp": 0, "adfox": 0, "kukuha": 0.0})
    for f in fact:
        a = acc[(f["campaign_id"], f["publisher_id"])]
        shows = int(f["shows"] or 0)
        if f["adfox"]:
            a["adfox"] += shows
            continue
        a["dsp"] += shows
        key = (f["publisher_id"], f["date"])
        tot, k = totals.get(key) or 0, kuk.get(key) or 0
        if f["publisher_id"] and tot > 0 and k > 0:
            # Доля не больше самих показов РК: блок за день не может дать РК больше, чем
            # она открутила на площадке всего.
            a["kukuha"] += min(shows, k * shows / tot)

    # CPM площадки по договору (закупочный, до НДС) — для денег на экране: показы × CPM / 1000.
    pubs = {r[0]: {"name": r[1], "domain": r[2], "cpm": r[3]} for r in db.execute(text(
        "SELECT id, name, domain, cpm_contract FROM sales_publishers WHERE id = ANY(:p)"),
        {"p": sorted({p for _, p in acc if p})}).all()}
    rows = []
    for (cid, pid), a in acc.items():
        c = camps[cid]
        # Округление «половина — вверх», как `round(numeric)` в витрине кабинета: иначе на
        # x,5 страница и кабинет разошлись бы на единицу (ревью 03.10.2026).
        kk = int(Decimal(str(a["kukuha"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total = a["dsp"] + a["adfox"]
        rows.append({
            "campaign_id": cid, "deal": c["deal"], "deal_id": c["deal_id"], "status": c["status"],
            "date_start": c["date_start"], "date_end": c["date_end"],
            "publisher_id": pid, "publisher": (pubs.get(pid) or {}).get("name") or "без площадки",
            "cpm": (pubs.get(pid) or {}).get("cpm"),
            "total": total, "dsp": a["dsp"], "adfox": a["adfox"], "kukuha": kk, "base": total - kk,
        })
    last = db.execute(text("SELECT max(date), max(fetched_at) FROM dsp_block_stat")).first()
    return {"rows": rows, "campaigns": len(camps), "period": period, "months": months(db),
            "kukuha_day": last[0] if last else None, "kukuha_fetched": last[1] if last else None}
