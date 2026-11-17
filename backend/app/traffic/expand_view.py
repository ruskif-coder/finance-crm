# -*- coding: utf-8 -*-
"""Расхлоп РК на дашборде трафика v2 (хендофф design_handoff_traffic_expand_v2, 17.11.2026): клики, CTR и расхождение
с Weborama по площадке, факт / клики / CTR по креативу на площадке.

Пороги — боевые (владелец 17.11.2026): уровень расхождения — `stat_sources.mismatch_level` с пределом из цели сделки,
своих 5/10 % из макета не вводим. Функции чистые и не меняют вход: ручка `/campaign/{id}` зовёт их над готовыми строками.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.ad.stat_sources import goal_limit, mismatch_level, mismatch_pct


def ctr_of(shows, clicks) -> Optional[float]:
    """CTR в процентах до сотых; без показов — None (прочерк, а не ноль: делить не на что)."""
    if not shows:
        return None
    return round((clicks or 0) / shows * 100, 2)


def _mismatch(own, wr, goals) -> Optional[dict]:
    pct = mismatch_pct(own, wr)
    return {"pct": pct, **mismatch_level(pct, goal_limit(goals))} if pct is not None else None


def enrich_placements(rows: List[dict], wr_by_placement: Dict[int, int], goals) -> List[dict]:
    """+ `ctr`, `wr` (показы верификатора за период), `wr_mismatch` {pct, level, …} — к каждой площадке."""
    out = []
    for r in rows:
        wr = wr_by_placement.get(r.get("id"))
        out.append({**r, "ctr": ctr_of(r.get("fact"), r.get("fact_clicks")), "wr": wr,
                    "wr_mismatch": _mismatch(r.get("fact"), wr, goals) if wr is not None else None})
    return out


def enrich_creatives(rows: List[dict], counts: Dict[int, list]) -> List[dict]:
    """+ `fact`, `clicks`, `ctr` к каждому креативу площадки — по его строке (пара креатив × площадка)."""
    out = []
    for r in rows:
        crs = []
        for c in r.get("creatives") or []:
            got = counts.get(c.get("id"))
            shows, clicks = (got[0], got[1]) if got else (None, None)
            crs.append({**c, "fact": shows, "clicks": clicks, "ctr": ctr_of(shows, clicks)})
        out.append({**r, "creatives": crs})
    return out


def erid_screens_by_campaign(db, campaign_ids) -> Dict[int, dict]:
    """Е и С в строке РК (v2, 17.11.2026): ЕРИД и скрины запуска по живым креативам всей РК — тем же правилом
    «нет / часть / все», что у площадки (`screens_tone`), одним запросом на весь реестр."""
    ids = list(campaign_ids or [])
    if not ids:
        return {}
    from sqlalchemy import text

    from app.ad.flight import CREATIVE_REJECTED, screens_tone
    acc: Dict[int, list] = {}
    for cid, status, has_erid, has_screens in db.execute(text(
            "SELECT campaign_id, status, erid IS NOT NULL AND erid <> '', screens_done_at IS NOT NULL "
            "FROM ad_campaign_creative WHERE campaign_id = ANY(:i)"), {"i": ids}).all():
        if status == CREATIVE_REJECTED:
            acc.setdefault(cid, [0, 0, 0])
            continue
        a = acc.setdefault(cid, [0, 0, 0])
        a[0] += 1
        a[1] += 1 if has_erid else 0
        a[2] += 1 if has_screens else 0
    return {cid: {"erid": screens_tone(e, n), "screens": screens_tone(sc, n)} for cid, (n, e, sc) in acc.items()}
