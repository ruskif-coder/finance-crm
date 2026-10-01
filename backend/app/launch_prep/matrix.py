"""Матрица «площадка × РК» для вкладки «Согласования» раздела «Паблишеры» (владелец 29.09.2026).

Две вкладки одного экрана на одних данных:

* **Согласования** — светофор на пересечении: где сейчас согласование комплекта этой РК
  с этой площадкой;
* **План площадок** — плановые показы площадки в РК и план себестоимости: показы ×
  закупочный CPM площадки из реестра паблишеров (`cpm_contract`, до НДС) / 1000.

Колонка — сделка с финансовым периодом в выбранном месяце (решение владельца: сделка,
а не бренд). Ячейка — получатель «Сбора запуска» (сделка × площадка × услуга); при
выборе «все услуги» несколько получателей одной пары сводятся по ХУДШЕМУ состоянию.

Только чтение: ни состояния, ни плана экран не меняет.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.launch_prep.withdraw import AGREED_STATES, PLACED_STATES

# Сколько рабочих дней площадка может молчать, прежде чем ячейка станет «просрочено».
LATE_WORKDAYS = 2

# «Согласовано» — всё от согласования и дальше по ступеням: те же списки, что у отзыва
# креатива (withdraw.py), чтобы граница «согласовано / нет» была одна на систему.
AGREED = AGREED_STATES + PLACED_STATES
REFUSED = "отказ площадки"

# Порядок «от худшего к лучшему» — по нему сводятся несколько услуг одной пары.
RANK = {"refused": 0, "late": 1, "rework": 2, "unsent": 3, "waiting": 4, "withdrawn": 5, "agreed": 6}


def workdays_between(start: date, end: date) -> int:
    """Рабочих дней после `start` до `end` включительно (выходные не считаются)."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def look(state: str, pairs: int, sent: int, withdrawn: int,
         waiting_since: Optional[datetime], today: date, rework: int = 0) -> dict:
    """Цвет ячейки и сколько дней ждём. Чистая функция — проверяется таблицей случаев.

    `rework` — пары, которые площадка вернула на доработку (сразу или отозвав согласование
    из кабинета, 29.09.2026). Если ждать от площадки больше нечего — мяч у аккаунта, и
    ячейка «на доработке», а не «ждём ответа»."""
    if state == REFUSED:
        return {"tone": "refused", "days": None}
    if withdrawn and withdrawn == pairs:
        return {"tone": "withdrawn", "days": None}
    if state in AGREED:
        return {"tone": "agreed", "days": None}
    if not sent:
        return {"tone": "unsent", "days": None}
    if rework and waiting_since is None:
        return {"tone": "rework", "days": None}
    days = workdays_between(waiting_since.date(), today) if waiting_since else 0
    return {"tone": "late" if days > LATE_WORKDAYS else "waiting", "days": days}


def _merge(a: dict, b: dict) -> dict:
    worse = b if RANK[b["tone"]] < RANK[a["tone"]] else a
    out = {k: a[k] + b[k] for k in ("pairs", "sent", "agreed", "withdrawn")}
    # Дни ожидания — самые долгие из сводимых строк, а не той, что оказалась хуже по цвету.
    days = max((x["days"] for x in (a, b) if x["days"] is not None), default=None)
    return {**worse, **out, "days": days if worse["days"] is not None else worse["days"],
            "services": a["services"] + b["services"],
            "states": a["states"] + b["states"]}


def month_bounds(month: str) -> tuple:
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start, end


def load(db: Session, month: str, service_id: Optional[int] = None,
         today: Optional[date] = None) -> dict:
    """Всё для обеих вкладок за месяц — пятью запросами на весь экран."""
    today = today or date.today()
    start, end = month_bounds(month)

    deals = db.execute(text("""
        SELECT d.id, d.code, coalesce(b.name, d.title) AS brand,
               coalesce(a.short_name, a.name) AS advertiser, r.name AS account,
               EXISTS (SELECT 1 FROM ad_campaign c WHERE c.deal_id = d.id
                                                    AND c.status = 'запущена') AS launched,
               (SELECT min(t.created_at) FROM launch_prep_target t WHERE t.deal_id = d.id) AS added_at
          FROM sales_deals d
          LEFT JOIN sales_brands b ON b.id = d.brand_id
          LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
          LEFT JOIN sales_reps r ON r.id = d.account_manager_id
         WHERE d.period_from >= :s AND d.period_from < :e
           AND EXISTS (SELECT 1 FROM launch_prep_target t WHERE t.deal_id = d.id)
         -- Запущенные РК впереди, внутри — в порядке добавления, ранние слева (владелец
         -- 01.10.2026). «Добавлена» — первый получатель сделки: номер сделки старше
         -- запуска (сделки из Битрикса), и по нему ранние оказывались справа.
         ORDER BY launched DESC, added_at, d.id
    """), {"s": start, "e": end}).mappings().all()
    ids = [d["id"] for d in deals]

    raw = db.execute(text("""
        SELECT t.deal_id, t.publisher_id, t.service_id, t.surface_kind, t.state,
               count(p.id) AS pairs, count(p.sent_at) AS sent,
               count(p.agreed_at) AS agreed, count(p.withdrawn_at) AS withdrawn,
               count(p.id) FILTER (WHERE r.verdict = 'на доработку'
                                     AND p.withdrawn_at IS NULL) AS rework,
               min(p.sent_at) FILTER (WHERE p.agreed_at IS NULL AND p.withdrawn_at IS NULL
                                        AND p.sent_at IS NOT NULL AND r.verdict IS NULL) AS waiting_since
          FROM launch_prep_target t
          LEFT JOIN launch_prep_pair p ON p.target_id = t.id
          LEFT JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind = 'площадка'
         WHERE t.deal_id = ANY(:ids)
         GROUP BY 1, 2, 3, 4, 5
    """), {"ids": ids}).mappings().all() if ids else []

    names = dict(db.execute(text("SELECT id, name FROM sales_services")).all())
    services = sorted({r["service_id"] for r in raw if r["service_id"]},
                      key=lambda s: names.get(s) or "")

    cells = {}
    for r in raw:
        if service_id and r["service_id"] != service_id:
            continue
        c = {**look(r["state"], r["pairs"], r["sent"], r["withdrawn"], r["waiting_since"], today,
                    r["rework"]),
             "pairs": r["pairs"], "sent": r["sent"], "agreed": r["agreed"],
             "withdrawn": r["withdrawn"],
             "services": [f'{names.get(r["service_id"]) or "—"} {(r["surface_kind"] or "").upper()}'.strip()],
             "states": [r["state"]]}
        key = (r["deal_id"], r["publisher_id"])
        cells[key] = _merge(cells[key], c) if key in cells else c

    # Скрины запуска по паре сделка × площадка — по креативам РК, кроме отклонённых
    # (владелец 01.10.2026; правило то же, что у индикатора «С» дашборда трафика).
    shots = {}
    if ids:
        from app.ad.flight import CREATIVE_REJECTED, screens_tone
        for d, p, total, got in db.execute(text("""
            SELECT c.deal_id, pl.publisher_id, count(cr.id), count(cr.screens_done_at)
              FROM ad_campaign c JOIN ad_campaign_placement pl ON pl.campaign_id = c.id
              JOIN ad_campaign_creative cr ON cr.placement_id = pl.id
             WHERE c.deal_id = ANY(:ids) AND cr.status <> :rej GROUP BY 1, 2
        """), {"ids": ids, "rej": CREATIVE_REJECTED}).all():
            shots[(d, p)] = screens_tone(got, total)

    plan = defaultdict(int)
    if ids:
        for d, p, shows in db.execute(text("""
            SELECT c.deal_id, pl.publisher_id, sum(pl.plan_show)
              FROM ad_campaign c JOIN ad_campaign_placement pl ON pl.campaign_id = c.id
             WHERE c.deal_id = ANY(:ids) GROUP BY 1, 2
        """), {"ids": ids}).all():
            plan[(d, p)] = int(shows or 0)

    # Все живые площадки, а не только участвующие в месяце: кнопка «Все площадки» показывает
    # и тех, кого нет ни в одной РК (пустые строки). Архив не считаем — правило проекта.
    pub_ids = sorted({p for _, p in cells})
    pubs = db.execute(text("""
        SELECT id, name, chat_url AS tg, chat_url_max AS max, cpm_contract AS cpm
          FROM sales_publishers WHERE status <> 'АРХИВ' OR id = ANY(:ids) ORDER BY lower(name)
    """), {"ids": pub_ids}).mappings().all()
    cpm = {p["id"]: p["cpm"] for p in pubs}

    used = {d for d, _ in cells}
    out_cells = []
    for (d, p), c in cells.items():
        shows = plan.get((d, p), 0)
        cost = round(shows * cpm[p] / 1000, 2) if shows and cpm.get(p) else None
        out_cells.append({"deal_id": d, "publisher_id": p, **c, "plan_show": shows,
                          "plan_cost": cost,
                          "screens": shots.get((d, p), {"state": "none", "got": 0, "total": 0})})
    return {
        "month": month, "today": today, "late_workdays": LATE_WORKDAYS,
        # План размещения ведётся на пару сделка × площадка, без разбивки по услугам:
        # при выбранной услуге экран обязан это сказать, а не выдавать план всех услуг за её.
        "plan_by_service": False,
        "services": [{"id": s, "name": names.get(s)} for s in services],
        "deals": [dict(d) for d in deals if d["id"] in used],
        "publishers": [dict(p) for p in pubs],
        "cells": out_cells,
    }


def months(db: Session, today: Optional[date] = None) -> list:
    """Месяцы, в которых есть что показать, плюс текущий — для переключателя периода."""
    today = today or date.today()
    got = {r[0] for r in db.execute(text("""
        SELECT DISTINCT to_char(d.period_from, 'YYYY-MM') FROM sales_deals d
         WHERE EXISTS (SELECT 1 FROM launch_prep_target t WHERE t.deal_id = d.id)
           AND d.period_from IS NOT NULL
    """)).all()}
    got.add(today.strftime("%Y-%m"))
    return sorted(got)
