# -*- coding: utf-8 -*-
"""Факт площадок для раскладки объёма (вход биддера, владелец 05.10.2026).

Факт — наш счётчик (`stat_sources.OWN`: DSP + ADFOX + ручной), с начала РК по дату среза.
Верификаторы (Weborama) не входят никогда. Срез устарел (ночной съём DSP не пришёл) —
возвращаем None, и раскладка идёт по весам, как до 05.10.2026: решать по позавчерашнему
факту хуже, чем не решать по факту вовсе.

Одна функция на всех: ночной пересчёт (`build.recompute_shares`) и оба дашборда, иначе
экран показывал бы один план, а в DSP уходил другой.
"""
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad.stat_sources import fact_as_of, fact_sources, is_stale


def placement_facts(db: Session, campaign_ids: Iterable[int]) -> Optional[dict]:
    """{campaign_id: {placement_id: показов}} или None, если факта за вчера нет."""
    ids = sorted({int(i) for i in campaign_ids if i is not None})
    # Пустая база: `fact_as_of` отдаёт «вчера» заглушкой — это не пришедшая статистика.
    if not _has_any_fact(db):
        return None
    as_of = fact_as_of(db)
    if is_stale(as_of):
        return None
    out: dict = {i: {} for i in ids}
    if not ids:
        return out
    for cid, pid, n in db.execute(text(
            "SELECT campaign_id, placement_id, sum(shows) FROM ad_campaign_stat "
            "WHERE campaign_id = ANY(:i) AND placement_id IS NOT NULL "
            "AND source = ANY(:src) AND date <= :d GROUP BY campaign_id, placement_id"),
            {"i": ids, "src": fact_sources(), "d": as_of}).all():
        out[cid][pid] = int(n or 0)
    return out


def _has_any_fact(db: Session) -> bool:
    return db.execute(text("SELECT EXISTS (SELECT 1 FROM ad_campaign_stat "
                           "WHERE source = ANY(:src))"), {"src": fact_sources()}).scalar()
