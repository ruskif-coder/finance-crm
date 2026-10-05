# -*- coding: utf-8 -*-
"""Отчёт клиенту по РК — данные (владелец 05.10.2026, план docs/ПЛАН_отчёт_клиенту_по_РК.md).

Аккаунт отправляет его клиенту, поэтому здесь только НАШ боевой факт (`stat_sources.COMBAT`:
DSP и Adfox) — Weborama не показываем, денег нет. Срезы — как в образце владельца: по
площадкам, по дням, по креативам × площадкам, по креативам × дням; в каждом показы и клики.
Охват — формулу даст владелец, пока его нет.

Период по умолчанию — от старта РК до последней даты, за которую есть данные; можно задать свой.

Откуда креатив:
* DSP — сырьё по креативу (`dsp_stat_raw` в аналитической базе), хеш → наша строка
  креатива через `stat_store.hash_map(...).rows` (текущие хеши + перевыгрузки из журнала);
* Adfox — разбивка импорта `adfox_creative_stat`.
Креатив в отчёте — комплект (`root_set_id`): один баннер на разных площадках — одна позиция.
Сумма креативов может быть меньше площадки: показы, которые DSP не разнесла по нашим
креативам, и дни Adfox, загруженные до 05.10.2026 без разбивки, в блоки креативов не попадают.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad.stat_sources import COMBAT

NO_PLACEMENT = "без площадки"


@dataclass
class Report:
    head: dict
    totals: dict
    by_placement: List[dict] = field(default_factory=list)
    by_day: List[dict] = field(default_factory=list)
    creatives: List[dict] = field(default_factory=list)   # [{label, by_placement, by_day}]
    # площадка → {день: показы} — для листа «По неделям» (владелец 05.10.2026)
    # площадка → {день: [показы, клики]} — для листа «По неделям» (владелец 05.10.2026)
    site_days: Dict[str, Dict[date, list]] = field(default_factory=dict)


def _row(label, shows, clicks, uniques=None) -> dict:
    return {"label": label, "shows": int(shows or 0), "clicks": int(round(clicks or 0)),
            "uniques": None if uniques is None else int(round(uniques))}


def head_of(db: Session, campaign_id: int) -> Optional[dict]:
    r = db.execute(text("""
        SELECT c.id, c.date_start, c.date_end, c.plan_show, c.ms_campaign_xxhash,
               d.id AS deal_id, d.code, d.title,
               coalesce(a.short_name, a.name) AS advertiser, b.name AS brand,
               coalesce(ag.short_name, ag.name) AS agency
          FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
          LEFT JOIN sales_brands b ON b.id = d.brand_id
          LEFT JOIN sales_agencies ag ON ag.id = d.agency_id
         WHERE c.id = :c"""), {"c": campaign_id}).mappings().first()
    return dict(r) if r else None


def period_of(*, start, end, first, last, date_from=None, date_to=None) -> dict:
    """Период отчёта и правый край колонок дней (ревью 05.10.2026).

    * начало — заданное, иначе старт РК, иначе первый день данных (у РК без дат был 500);
    * конец цифр — заданный, иначе последний день данных;
    * колонки дней — по умолчанию до конца флайта (будущие пустые), но не короче последнего
      дня данных: докрутка после конца флайта и РК без даты окончания не теряют дни;
      при заданном периоде — ровно по нему.
    """
    d1 = date_from or start or first
    d2 = date_to or last or end or d1
    if date_to:
        days_to = date_to
    else:
        days_to = max(x for x in (end, last, d2, d1) if x) if (d1 or d2) else None
    return {"from": d1, "to": d2, "days_to": days_to}


def first_data_day(db: Session, campaign_id: int) -> Optional[date]:
    return db.execute(text(
        "SELECT min(date) FROM ad_campaign_stat WHERE campaign_id = :c AND source = ANY(:s) "
        "AND shows > 0"), {"c": campaign_id, "s": list(COMBAT)}).scalar()


def last_data_day(db: Session, campaign_id: int) -> Optional[date]:
    return db.execute(text(
        "SELECT max(date) FROM ad_campaign_stat WHERE campaign_id = :c AND source = ANY(:s) "
        "AND shows > 0"), {"c": campaign_id, "s": list(COMBAT)}).scalar()


def deal_report_ready(db: Session, deal_id: int) -> bool:
    """Отчёт клиенту доступен, только когда у РК сделки есть статистика хотя бы за день
    (владелец 05.10.2026) — пустой отчёт клиенту не отправляют."""
    return bool(db.execute(text("""
        SELECT 1 FROM ad_campaign c JOIN ad_campaign_stat s ON s.campaign_id = c.id
         WHERE c.deal_id = :d AND s.source = ANY(:s) AND s.shows > 0 LIMIT 1"""),
        {"d": deal_id, "s": list(COMBAT)}).first())


def _creative_labels(db: Session, campaign_id: int) -> Dict[int, tuple]:
    """строка креатива → (ключ комплекта, подпись, площадка). Подпись — «Креатив №N · название»."""
    out = {}
    for cid, set_id, no, title, domain, pname in db.execute(text("""
        SELECT cr.id, coalesce(cr.root_set_id, cs.id), coalesce(cs.no, cr.creative_no),
               cs.title, p.domain, p.name
          FROM ad_campaign_creative cr
          LEFT JOIN launch_prep_pair pr ON pr.id = cr.pair_id
          LEFT JOIN launch_prep_creative_set cs ON cs.id = coalesce(cr.root_set_id, pr.set_id)
          LEFT JOIN ad_campaign_placement pl ON pl.id = cr.placement_id
          LEFT JOIN sales_publishers p ON p.id = pl.publisher_id
         WHERE cr.campaign_id = :c"""), {"c": campaign_id}).all():
        label = f"Креатив №{no}" + (f" · {title.strip()}" if title and title.strip() else "")
        out[cid] = (set_id or f"no{no}", label, domain or pname or NO_PLACEMENT, no or 0)
    return out


def _dsp_creative_days(db: Session, dsp_db, camp: dict, d1: date, d2: date) -> Dict[tuple, list]:
    """(строка креатива, день) → [показы, клики] из сырья DSP."""
    if dsp_db is None or not camp.get("ms_campaign_xxhash"):
        return {}
    from app.dsp import stat_store
    from app.dsp.client import PROD, MsClient
    cl = MsClient(contour=PROD)
    hmap = stat_store.hash_map(db, dsp_db, [camp["id"]], contour=cl.contour,
                               partner=cl.partner_xxhash)
    out: Dict[tuple, list] = {}
    for day, cr, shows, clicks in dsp_db.execute(text("""
        SELECT (ts AT TIME ZONE 'Europe/Moscow')::date, ms_creative_xxhash, shows, clicks
          FROM dsp_stat_raw
         WHERE ms_campaign_xxhash = :h AND ms_source_key IS NULL AND ms_creative_xxhash IS NOT NULL
           AND (ts AT TIME ZONE 'Europe/Moscow')::date BETWEEN :a AND :b"""),
            {"h": camp["ms_campaign_xxhash"].upper(), "a": d1, "b": d2}).all():
        rid = hmap.rows.get((cr or "").upper())
        if rid is None:
            continue
        acc = out.setdefault((rid, day), [0, 0])
        acc[0] += shows or 0
        acc[1] += clicks or 0
    return out


def build(db: Session, campaign_id: int, date_from: Optional[date] = None,
          date_to: Optional[date] = None, dsp_db=None, model: bool = False) -> Optional[Report]:
    """`model=True` — комплект «с поправкой» (SIMB ID, владелец 05.10.2026): показы те же,
    реальные; клики и уники — от коэффициентов пары «площадка × креатив» за день
    (`report_coef`, фиксируются разово). Показы, которые не разнесены по креативам, получают
    базовые коэффициенты без поправки."""
    camp = head_of(db, campaign_id)
    if camp is None:
        return None
    last = last_data_day(db, campaign_id)
    per_ = period_of(start=camp["date_start"], end=camp["date_end"],
                     first=first_data_day(db, campaign_id), last=last,
                     date_from=date_from, date_to=date_to)
    d1, d2 = per_["from"], per_["to"]
    src = list(COMBAT)

    # ── площадки и дни: факт системы ────────────────────────────────────────
    rows = db.execute(text("""
        SELECT s.date, coalesce(p.domain, p.name) AS site, sum(s.shows) AS shows, sum(s.clicks) AS clicks
          FROM ad_campaign_stat s
          LEFT JOIN ad_campaign_placement pl ON pl.id = s.placement_id
          LEFT JOIN sales_publishers p ON p.id = pl.publisher_id
         WHERE s.campaign_id = :c AND s.source = ANY(:s) AND s.date BETWEEN :a AND :b
         GROUP BY 1, 2"""), {"c": campaign_id, "s": src, "a": d1, "b": d2}).mappings().all()
    # ── креативы: DSP-сырьё + разбивка Adfox ────────────────────────────────
    labels = _creative_labels(db, campaign_id)
    per: Dict[tuple, list] = dict(_dsp_creative_days(db, dsp_db, camp, d1, d2))
    for cid, day, shows, clicks in db.execute(text("""
        SELECT a.creative_id, a.date, a.shows, a.clicks FROM adfox_creative_stat a
          JOIN ad_campaign_creative cr ON cr.id = a.creative_id
         WHERE cr.campaign_id = :c AND a.date BETWEEN :a AND :b"""),
            {"c": campaign_id, "a": d1, "b": d2}).all():
        acc = per.setdefault((cid, day), [0, 0])
        acc[0] += shows or 0
        acc[1] += clicks or 0
    per = {k: v for k, v in per.items() if k[0] in labels and (v[0] or v[1])}

    # ── модель SIMB ID: клики и уники пары-дня от реальных показов ──────────
    settings = None
    if model:
        from app.ad import report_coef
        from app.routers.simb_id import load as load_settings
        settings = load_settings(db)
        coefs = report_coef.ensure(db, [k for k, v in per.items() if v[0]], settings)
        for k, v in per.items():
            d = report_coef.derive(v[0], coefs[k]) if k in coefs else {"uniques": 0, "clicks": 0}
            per[k] = [v[0], d["clicks"], d["uniques"]]
    pair_site_day: Dict[tuple, list] = defaultdict(lambda: [0, 0, 0])
    for (cid, day), v in per.items():
        acc = pair_site_day[(labels[cid][2], day)]
        for i, x in enumerate(v):
            acc[i] += x or 0

    # ── площадки и дни: факт системы (в модели — клики/уники из пар + остаток по базе) ─
    by_site: Dict[str, list] = defaultdict(lambda: [0, 0, 0])
    by_day: Dict[date, list] = defaultdict(lambda: [0, 0, 0])
    site_days: Dict[str, Dict[date, list]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        site, day, sh = r["site"] or NO_PLACEMENT, r["date"], r["shows"] or 0
        if model:
            pv = pair_site_day.get((site, day), [0, 0, 0])
            rest = max(0, sh - pv[0])
            ck = pv[1] + rest * settings["ctr_base"] / 100
            un = pv[2] + (rest / settings["freq_base"] if settings["freq_base"] else 0)
        else:
            ck, un = r["clicks"] or 0, 0
        site_days[site][day][0] += sh
        site_days[site][day][1] += ck
        for acc in (by_site[site], by_day[day]):
            acc[0] += sh
            acc[1] += ck
            acc[2] += un

    groups: Dict[object, dict] = {}
    for (cid, day), v in per.items():
        key, label, site, no = labels[cid]
        g = groups.setdefault(key, {"label": label, "no": no,
                                    "site": defaultdict(lambda: [0, 0, 0]),
                                    "day": defaultdict(lambda: [0, 0, 0]),
                                    "site_day": defaultdict(lambda: defaultdict(lambda: [0, 0]))})
        g["site_day"][site][day][0] += v[0]
        g["site_day"][site][day][1] += v[1] or 0
        for acc in (g["site"][site], g["day"][day]):
            for i in range(3):
                acc[i] += (v[i] if i < len(v) else 0) or 0

    def mk(k, v):
        return _row(k, v[0], v[1], v[2] if model else None)

    def site_rows(m):
        return [mk(k, v) for k, v in sorted(m.items(), key=lambda x: (-x[1][0], x[0]))]

    def day_rows(m):
        return [mk(k, v) for k, v in sorted(m.items())]

    shows = sum(v[0] for v in by_site.values())
    clicks = int(round(sum(v[1] for v in by_site.values())))
    plan = int(camp["plan_show"] or 0) or None
    return Report(
        head={**camp, "period_from": d1, "period_to": d2, "last_data": last,
              # колонки дней — до конца флайта, если период не задан (будущие дни пустые)
              "to_flight_end": date_to is None, "model": model,
              "days_to": per_["days_to"]},
        totals={"shows": shows, "clicks": clicks,
                "ctr": round(clicks / shows * 100, 2) if shows else None,
                "plan": plan, "done_pct": round(shows / plan * 100, 1) if plan else None},
        by_placement=site_rows(by_site),
        by_day=day_rows(by_day),
        site_days={k: dict(v) for k, v in site_days.items()},
        creatives=[{"label": g["label"], "by_placement": site_rows(g["site"]),
                    "by_day": day_rows(g["day"]),
                    "site_days": {k: dict(v) for k, v in g["site_day"].items()}}
                   for g in sorted(groups.values(), key=lambda g: (g["no"], g["label"]))],
    )
