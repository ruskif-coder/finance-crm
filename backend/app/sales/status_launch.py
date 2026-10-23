# -*- coding: utf-8 -*-
"""«Статусы продаж»: реальный старт, опоздание старта и темп к закрытию (владелец 23.10.2026).

· Реальный старт: полный цикл — первый день с показами в боевой статистике РК (`fact_sources`); контур аккаунта (внешние
  услуги) — кнопка «Запустить», то есть первый вход на «В размещении».
· Опоздание: сделка на «Готовятся к старту» / «В размещении», реального старта нет, а с планового прошло 7 дней — «warn»,
  14 — «bad». Плановый старт — начало флайта РК, без РК — начало периода сделки.
· Темп: доля прогноза открутки к плану для полного цикла (тот же линейный прогноз, что у дашборда трафика,
  `app/ad/flight.forecast_of`, от даты среза статистики), не больше 1; внешние услуги, РК без прогноза и сделки,
  закрытые итоговой сверкой «по плану», — 1 (100 %)."""
from datetime import date
from typing import Optional

from sqlalchemy import text

WARN_DAYS, BAD_DAYS = 7, 14
ON_START = ("launch_prep", "launch")


def late(stage_key: Optional[str], plan_start: Optional[date], real_start: Optional[date], today: date) -> tuple:
    """(None | "warn" | "bad", дней с планового старта)."""
    if stage_key not in ON_START or real_start or not plan_start:
        return None, 0
    days = (today - plan_start).days
    return ("bad" if days >= BAD_DAYS else "warn" if days >= WARN_DAYS else None), max(days, 0)


def pace_ratio(full_cycle: bool, plan: Optional[float], fact: Optional[float],
               start: Optional[date], end: Optional[date], today: date) -> float:
    if not full_cycle:
        return 1.0
    from app.ad.flight import flight_of, forecast_of
    fc = forecast_of(plan, fact, flight_of(start, end, today))
    return 1.0 if fc is None else max(0.0, min(1.0, fc / plan))


def collect(db, rows, today: date) -> dict:
    """{id сделки: {plan_start, real_start, late, late_days, pace, full}} по строкам с полями
    id, stage_key, period_from, realization_pipeline_id, service_id — пачкой, без запроса на сделку."""
    from app.ad.stat_sources import fact_as_of, fact_sources
    from app.final_recon import flow
    from app.sales.deal_delivery import campaigns_by_deal
    from app.traffic.delivery_facts import _facts
    ids = [r.id for r in rows]
    if not ids:
        return {}
    camps = campaigns_by_deal(db, ids)
    cids = [c.id for c in camps.values()]
    facts = _facts(db, cids)
    first_stat = dict(db.execute(text(
        "SELECT c.deal_id, min(s.date) FROM ad_campaign_stat s JOIN ad_campaign c ON c.id = s.campaign_id "
        "WHERE c.deal_id = ANY(:i) AND s.source = ANY(:src) AND s.shows > 0 GROUP BY c.deal_id"),
        {"i": ids, "src": fact_sources()}).all())
    # Прогноз — от даты среза статистики, как у дашборда трафика: факт «по вчера» против дней «по сегодня» занижал бы темп
    cut = fact_as_of(db, today)
    # Итоговая сверка закрыла сделку «по плану» — к закрытию идёт план, недокрут не вычитается
    by_plan = {r[0] for r in db.execute(text(
        "SELECT deal_id FROM final_recon_deals WHERE deal_id = ANY(:i) AND confirmed_at IS NOT NULL AND ds_mode = 'plan'"),
        {"i": ids}).all()}
    first_launch = dict(db.execute(text(
        "SELECT h.deal_id, (min(h.at) AT TIME ZONE 'Europe/Moscow')::date FROM sales_deal_stage_history h JOIN sales_stages s ON s.id = h.to_stage_id "
        "WHERE h.deal_id = ANY(:i) AND s.stage_key = 'launch' GROUP BY h.deal_id"), {"i": ids}).all())
    out = {}
    for r in rows:
        full = flow.of_ids(db, r.realization_pipeline_id, r.service_id) == flow.FULL
        c = camps.get(r.id)
        plan_start = (c.date_start if c and c.date_start else r.period_from)
        real = first_stat.get(r.id) if full else first_launch.get(r.id)
        lvl, days = late(r.stage_key, plan_start, real, today)
        f = facts.get(c.id) if c else None
        pace = 1.0 if r.id in by_plan else pace_ratio(
            full, float(c.plan_show) if c and c.plan_show else None,
            float(f["shows"]) if f and f.get("shows") is not None else None,
            c.date_start if c else None, c.date_end if c else None, cut)
        out[r.id] = {"plan_start": plan_start.isoformat() if plan_start else None,
                     "real_start": real.isoformat() if real else None, "late": lvl, "late_days": days,
                     "pace": round(pace, 4), "full": full}
    return out
