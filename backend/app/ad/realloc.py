# -*- coding: utf-8 -*-
"""«Темп размещения → Перераспределить» (владелец 24.10.2026).

Подсказка «темп к плану — перераспределить» не говорила, ЧТО двигать. Недокрут бывает разный, и переносить объём
имеет смысл только в одном случае — площадка упёрлась в СЕТЬ: ей предлагают меньше, чем нужно в день (`pace`
«мало трафика» / «нет трафика»). Её недобор до конца флайта уходит площадкам, которые идут в темпе и которым
предлагают больше нужного. Площадка «трафик есть, не открутили» — не донор: у неё упор в лимит или креатив, это
лечит «Поднять темп» или проверка креатива.

Правила (`propose`, чистая функция):
  · остаток = план − факт; успеет = возможность в день (медиана предложенного, `pace.assess.capacity`) × дни до конца;
  · донор отдаёт остаток − успеет; получатель берёт не больше половины неиспользованного предложения
    ((возможность − нужно в день) × дни × SPARE_USE) — предложенное не равно откручиваемому;
  · переносится min(отдают, берут), пропорционально; непристроенное называется отдельно («нужны площадки»);
  · сумма планов не меняется, план не ниже факта; не запущенные, на паузе и с неизвестным предложением — как есть.

Применение (`apply`) пишет новые планы в `ad_campaign_placement.fixed_plan` — их держит раскладка как заданный
объём — и сразу шлёт лимиты креативов в DSP, как «Поднять темп». `reset` возвращает площадки РК на веса.
"""
from __future__ import annotations

from typing import List, Optional

DONOR_PACE = ("мало трафика", "нет трафика")
TAKER_PACE = ("в темпе", "перебор")
SPARE_USE = 0.5
IN_WORK = ("запущен", "пауза")
BOOST_LIVE = ("Идёт «Поднять темп» — планы площадок сейчас подняты на его процент, и записать их ручными значит "
              "продлить буст навсегда и перекрутить план РК. Снимите буст или дождитесь его конца.")

NOTE_NOT_DELIVERED = "трафик есть, а показов меньше нужного — недобор не из-за сети: поднимите темп или проверьте креатив"
NOTE_UNKNOWN = "предложение сети неизвестно (Adfox или нет данных) — не трогаем"


def propose(rows: List[dict], days_left: int) -> dict:
    """rows: [{id, name, plan, fact, capacity (в день или None), pace (статус суток), running}]."""
    L = max(0, int(days_left or 0))
    out, give, take = [], {}, {}
    for r in rows:
        plan, fact = float(r.get("plan") or 0), float(r.get("fact") or 0)
        rest = max(0.0, plan - fact)
        need = rest / L if L else 0.0
        cap = r.get("capacity")
        row = {**r, "plan": round(plan), "fact": round(fact), "rest": round(rest), "need": round(need),
               "plan_new": round(plan), "delta": 0, "role": "без изменений", "note": None}
        if r.get("running") and L and rest:
            if r.get("pace") in DONOR_PACE:
                can = (cap or 0) * L
                if can < rest:
                    give[r["id"]] = rest - can
                    row["note"] = f"успеет ~{round(can):,} из {round(rest):,}".replace(",", " ")
            elif r.get("pace") in TAKER_PACE and cap is not None and cap > need:
                take[r["id"]] = (cap - need) * L * SPARE_USE
                row["role"] = "запас"
            elif r.get("pace") == "трафик есть, не открутили":
                row["note"] = NOTE_NOT_DELIVERED
            elif cap is None:
                row["note"] = NOTE_UNKNOWN
        out.append(row)
    G, S = sum(give.values()), sum(take.values())
    moved = int(min(G, S))
    if moved:
        by = {r["id"]: r for r in out}
        for pid, g in give.items():
            d = round(g * moved / G)
            by[pid].update(plan_new=by[pid]["plan"] - d, delta=-d, role="донор")
        takers = list(take.items())
        given = 0
        for i, (pid, t) in enumerate(takers):
            d = moved - given if i == len(takers) - 1 else round(t * moved / S)
            given += d
            by[pid].update(plan_new=by[pid]["plan"] + d, delta=d, role="получатель")
        # Округление доноров: сумма планов РК сходится до показа
        drift = sum(r["plan_new"] for r in out) - sum(r["plan"] for r in out)
        if drift and give:
            pid = max(give, key=give.get)
            by[pid]["plan_new"] -= drift
            by[pid]["delta"] -= drift
    for r in out:   # «нужно в сутки» после переноса — тем же правилом: (новый план − факт) ÷ дни до конца
        r["need_new"] = round(max(0, r["plan_new"] - r["fact"]) / L) if L else 0
    return {"rows": out, "moved": moved, "unplaced": round(G - moved), "shortfall": round(G),
            "spare": round(S), "days_left": L}


def rows_of(db, camp, as_of=None) -> tuple:
    """Площадки РК для расчёта: записанный план, факт (OWN), возможность и статус темпа. → (rows, дней до конца)."""
    from app.ad import pace
    from app.ad.flight import flight_of
    from app.ad.models import AdCampaignPlacement
    from app.ad.stat_sources import fact_as_of
    from app.bidder.facts import any_facts
    from app.routers.traffic_dashboard import _pace_of
    from datetime import date
    as_of = as_of or fact_as_of(db, date.today())
    fl = flight_of(camp.date_start, camp.date_end, as_of)
    pls = (db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == camp.id)
           .order_by(AdCampaignPlacement.id).all())
    names = _names(db, [p.publisher_id for p in pls])
    # Последний известный факт, даже если среза за вчера нет: иначе остаток считался бы от нуля (как у буста)
    facts = any_facts(db, camp.id)
    base = [{"id": p.id, "plan_show": p.plan_show} for p in pls]
    pc = _pace_of(db, camp, base, as_of)
    rows = []
    for p in pls:
        a = pc.get(p.id) or {}
        rows.append({"id": p.id, "name": names.get(p.publisher_id, str(p.publisher_id)), "status": p.status,
                     "running": p.status in ("запущен",), "plan": p.plan_show or 0, "fact": facts.get(p.id, 0),
                     "capacity": a.get("capacity"), "pace": a.get("status") or pace.IN_PACE if a else None,
                     # последние отчитанные сутки — те же числа, что в подсказке колонки «Темп» дашборда
                     "day": a.get("day"), "shows_day": a.get("shows"), "offered_day": a.get("offered"),
                     "chronic": bool(a.get("chronic")),
                     "fixed_plan": p.fixed_plan})
    return rows, (fl.left if fl else 0)


def _names(db, pub_ids) -> dict:
    from sqlalchemy import text
    if not pub_ids:
        return {}
    return dict(db.execute(text("SELECT id, coalesce(domain, name) FROM sales_publishers WHERE id = ANY(:i)"),
                           {"i": list(set(pub_ids))}).all())


def apply(db, camp, plans: dict, user, client=None) -> dict:
    """Записать ручные планы площадок РК и сразу отправить лимиты креативов в DSP. `plans` = {id площадки: план}.
    Проверки — у вызывающего (`check_plans`)."""
    from app.ad import build
    from app.ad.boost_apply import _sync
    from app.ad.models import AdCampaignPlacement
    from app.ext_lock import lock_campaign_shares
    lock_campaign_shares(db, camp.id)
    for p in db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == camp.id,
                                                  AdCampaignPlacement.id.in_(list(plans))):
        p.fixed_plan = float(plans[p.id])
    db.flush()
    changes = build.recompute_shares(db, camp.id)
    db.commit()
    return {"changes": len(changes), "dsp": _sync(db, camp, client)}


def reset(db, camp, client=None) -> dict:
    """Снять ручные планы РК — площадки снова по весам."""
    from app.ad import build
    from app.ad.boost_apply import _sync
    from app.ad.models import AdCampaignPlacement
    from app.ext_lock import lock_campaign_shares
    lock_campaign_shares(db, camp.id)
    n = (db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == camp.id,
                                              AdCampaignPlacement.fixed_plan.isnot(None))
         .update({AdCampaignPlacement.fixed_plan: None}, synchronize_session=False))
    db.flush()
    build.recompute_shares(db, camp.id)
    db.commit()
    return {"reset": n, "dsp": _sync(db, camp, client)}


def check_plans(rows: List[dict], plans: dict, camp_plan: Optional[float]) -> Optional[str]:
    """Текст отказа или None: площадка из этой РК и в работе (запущена или на паузе), план не ниже факта, сумма планов
    ВСЕХ площадок РК после правки не больше плана РК — лимит РК не выходит за план (владелец 24.10.2026)."""
    by = {r["id"]: r for r in rows}
    for pid, v in plans.items():
        r = by.get(pid)
        if r is None:
            return "Площадка не из этой РК"
        if r.get("status") not in IN_WORK:
            return f"{r['name']}: площадка не в работе ({r.get('status')}) — ручной план только у запущенных и на паузе"
        if v is None or v < 0:
            return f"{r['name']}: план не задан"
        if v < r["fact"]:
            return f"{r['name']}: план {round(v):,} меньше уже открученного {round(r['fact']):,}".replace(",", " ")
    total = sum(float(plans.get(r["id"], r["plan"]) or 0) for r in rows)
    if camp_plan and total > camp_plan * 1.001:
        return f"Сумма планов площадок {round(total):,} больше плана РК {round(camp_plan):,}".replace(",", " ")
    return None
