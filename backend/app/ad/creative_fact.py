# -*- coding: utf-8 -*-
"""Факт по КРЕАТИВАМ РК — одна точка (владелец 24.10.2026).

В основной базе факт лежит по площадкам (`ad_campaign_stat`). По креативам его знают только сырьё DSP (аналитическая
база, хеш креатива → наша строка через `stat_store.hash_map`, с перевыгрузками из журнала) и разбивка Adfox
(`adfox_creative_stat`). Читают: отчёт клиенту (креатив × день) и раскладка лимитов креативов (итог за РК) — креатив,
добавленный в середине РК, получает долю ОСТАТКА площадки, а не половину плана (`flight.split_evenly`).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, Optional

from sqlalchemy import text

log = logging.getLogger("finance.ad")


def dsp_days(db, dsp_db, campaign_id: int, ms_campaign_xxhash: Optional[str],
             d1: Optional[date] = None, d2: Optional[date] = None) -> Dict[tuple, list]:
    """(строка креатива, день МСК) → [показы, клики] из сырья DSP. Нет сырья или хеша РК — пусто."""
    if dsp_db is None or not ms_campaign_xxhash:
        return {}
    from app.dsp import stat_store
    from app.dsp.client import PROD, MsClient
    cl = MsClient(contour=PROD)
    hmap = stat_store.hash_map(db, dsp_db, [campaign_id], contour=cl.contour, partner=cl.partner_xxhash)
    out: Dict[tuple, list] = {}
    for day, cr, shows, clicks in dsp_db.execute(text("""
        SELECT (ts AT TIME ZONE 'Europe/Moscow')::date, ms_creative_xxhash, sum(shows), sum(clicks)
          FROM dsp_stat_raw
         WHERE ms_campaign_xxhash = :h AND ms_source_key IS NULL AND ms_creative_xxhash IS NOT NULL
           AND (CAST(:a AS date) IS NULL OR (ts AT TIME ZONE 'Europe/Moscow')::date >= :a)
           AND (CAST(:b AS date) IS NULL OR (ts AT TIME ZONE 'Europe/Moscow')::date <= :b)
         GROUP BY 1, 2"""), {"h": ms_campaign_xxhash.upper(), "a": d1, "b": d2}).all():
        rid = hmap.rows.get((cr or "").upper())
        if rid is None:
            continue
        acc = out.setdefault((rid, day), [0, 0])
        acc[0] += shows or 0
        acc[1] += clicks or 0
    return out


class FactUnavailable(Exception):
    """Факт креативов из аналитики DSP не прочитан — `strict`-вызов не должен решать по неполному факту."""


def totals(db, camp, dsp_db=None, strict: bool = False) -> Dict[int, int]:
    """{строка креатива: показы за всю РК} — DSP + Adfox. Аналитика недоступна — только Adfox: раскладка тогда
    делит остаток как раньше, поровну, а не обнуляет лимиты (сбой чтения не должен останавливать креативы).
    `strict` — для ОТПРАВКИ лимитов в DSP (ревью 27.10.2026): деление поровну без факта поднимало лимит новому креативу,
    пока старый уже открутил почти всё, — перекрут. Там сбой чтения — исключение, и лимиты РК не трогаются."""
    out: Dict[int, int] = {}
    for cid, shows in db.execute(text("""
        SELECT a.creative_id, sum(a.shows) FROM adfox_creative_stat a
          JOIN ad_campaign_creative cr ON cr.id = a.creative_id
         WHERE cr.campaign_id = :c GROUP BY 1"""), {"c": camp.id}).all():
        out[cid] = out.get(cid, 0) + int(shows or 0)
    if not getattr(camp, "ms_campaign_xxhash", None):
        return out
    own = None
    try:
        if dsp_db is None:
            from app.dsp.db import DspSessionLocal
            if DspSessionLocal is None:
                return out
            dsp_db = own = DspSessionLocal()
        for (rid, _day), v in dsp_days(db, dsp_db, camp.id, camp.ms_campaign_xxhash).items():
            out[rid] = out.get(rid, 0) + int(v[0] or 0)
    except Exception as e:     # аналитика — подсказка раскладке, а не условие: без неё — поровну
        log.warning("факт креативов РК %s не прочитан: %s", camp.id, e)
        if strict:
            raise FactUnavailable(str(e)) from e
    finally:
        if own is not None:
            own.close()
    return out
