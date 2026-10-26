# -*- coding: utf-8 -*-
"""«Темп размещения → Перераспределить» (владелец 24.10.2026).

Подсказка «темп к плану — перераспределить» не говорила, ЧТО двигать. Недокрут бывает разный, и переносить объём
имеет смысл только в одном случае — площадка упёрлась в СЕТЬ: ей предлагают меньше, чем нужно в день (`pace`
«мало трафика» / «нет трафика»). Её недобор до конца флайта уходит площадкам, которые идут в темпе и которым
предлагают больше нужного. Площадка «трафик есть, не открутили» — не донор: у неё упор в лимит или креатив, это
лечит «Поднять темп» или проверка креатива.

Правила (`propose`, чистая функция):
  · остаток = план − факт; успеет = возможность в день (медиана предложенного, `pace.assess.capacity`) × дни до конца;
  · донор отдаёт остаток − успеет; получатель берёт не больше неиспользованной возможности
    ((возможность − нужно в день) × дни × SPARE_USE) — вся возможность (владелец 26.10.2026: «как в макете»; до того ½);
  · переносится min(отдают, берут), пропорционально; непристроенное называется отдельно («нужны площадки»);
  · сумма планов не меняется, план не ниже факта; не запущенные, на паузе и с неизвестным предложением — как есть.

Применение (`apply`) пишет новые планы в `ad_campaign_placement.fixed_plan` — их держит раскладка как заданный
объём — и сразу шлёт лимиты креативов в DSP, как «Поднять темп». `reset` возвращает площадки РК на веса.
"""
from __future__ import annotations

import re
from typing import List, Optional

DONOR_PACE = ("мало трафика", "нет трафика")
TAKER_PACE = ("в темпе", "перебор")
SPARE_USE = 1.0
REASON_MAX = 300
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
    from sqlalchemy import text
    from app.ad.build import PLACEMENT_FIXED_SQL
    fixed = dict(db.execute(text(f"SELECT p.id, {PLACEMENT_FIXED_SQL} FROM ad_campaign_placement p WHERE p.campaign_id = :c"),
                            {"c": camp.id}).all())
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
                     "fixed_plan": p.fixed_plan, "fixed": fixed.get(p.id)})
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
    # Перенос сохраняет сумму (хендофф 26.10.2026): сколько отдали — столько взяли, план РК не меняется.
    before = sum(float(r["plan"] or 0) for r in rows)
    if abs(total - before) > 1:
        d = total - before
        return (f"План РК не сходится на {'+' if d > 0 else '−'}{round(abs(d)):,} — перенос должен сохранять сумму "
                f"планов ({round(before):,})").replace(",", " ")
    return None


def check_reason(reason: Optional[str]) -> Optional[str]:
    """Причина переноса обязательна — уходит в журнал РК и в историю окна (хендофф 26.10.2026)."""
    r = (reason or "").strip()
    if not r:
        return "Укажите причину переноса — она уйдёт в журнал РК"
    if len(r) > REASON_MAX:
        return f"Причина длиннее {REASON_MAX} символов"
    return None


def journal_text(label: str, rows: List[dict], plans: dict, reason: str) -> str:
    """Строка журнала: «РК X: перенесено N · площадка −d; площадка +d · причина: «…»» — её же разбирает `history_of`."""
    by = {r["id"]: r for r in rows}
    moves = [(by[k]["name"], round(float(v) - float(by[k]["plan"] or 0))) for k, v in plans.items()]
    moved = sum(-d for _n, d in moves if d < 0)
    parts = "; ".join(f"{n} {'+' if d > 0 else '−'}{abs(d):,}" for n, d in sorted(moves, key=lambda x: x[1]) if d)
    return (f"{label}: перенесено {moved:,} · {parts} · причина: «{reason.strip()}»").replace(",", " ")


_JOURNAL = re.compile(r"^[^:]*:\s*(?:перенесено\s+(?P<moved>[\d\s]+)\s+·\s+)?(?P<what>.*?)(?:\s+·\s+причина:\s+«(?P<why>.*)»)?$")


def history_of(rows: List[dict]) -> List[dict]:
    """Записи журнала РК («traffic_realloc», «traffic_realloc_reset») → строки истории окна: когда, кто, объём, что, почему.
    Старые записи без объёма и причины показываются как есть."""
    out = []
    for r in rows:
        m = _JOURNAL.match(r.get("details") or "")
        moved = m.group("moved") if m else None
        at = r.get("created_at")
        out.append({"at": at.isoformat() if hasattr(at, "isoformat") else at, "who": r.get("user_name"),
                    "action": r.get("action"),
                    "moved": int(moved.replace(" ", "")) if moved else None,
                    "what": (m.group("what") if m else r.get("details")) or "",
                    "why": m.group("why") if m else None})
    return out


# ── Сценарии-кнопки окна (владелец 26.10.2026): вместо таблицы с ручными полями — готовые действия по логике ──────────
#
# Каждый сценарий — одна понятная операция с тем, что она сделает, и почему её сейчас нельзя, если нельзя. Сами действия —
# существующие ручки (перераспределение, «Поднять темп» по площадкам, статус площадки, сброс); здесь только выбор,
# чтобы экран не держал второго правила.

NOT_DELIVERED = "трафик есть, не открутили"
NO_TRAFFIC = "нет трафика"
LAG_MIN_PCT = 5


def _lag_pct(rows: List[dict], days_left: int) -> int:
    """Процент буста, чтобы самая отстающая из выбранных площадок вышла на «нужно в день» — но не выше того, что сеть
    предлагает (поднимать лимит над предложением бессмысленно) и не выше потолка буста."""
    from app.ad.boost import MAX_PCT
    best = 0.0
    for r in rows:
        shows = float(r.get("shows_day") or 0)
        need = max(0.0, float(r.get("plan") or 0) - float(r.get("fact") or 0)) / days_left if days_left else 0.0
        offered = r.get("offered_day")
        want = min(need, float(offered)) if offered is not None else need
        best = max(best, MAX_PCT if shows <= 0 else (want / shows - 1) * 100)
    pct = int(round(best / LAG_MIN_PCT) * LAG_MIN_PCT)
    return max(LAG_MIN_PCT, min(MAX_PCT, pct))


def scenarios(rows: List[dict], out: dict, days_left: int, *, boost_live: bool = False, has_manual: bool = False,
              closed: bool = False, boost_days: Optional[int] = None, over_plan: Optional[dict] = None) -> List[dict]:
    """Четыре сценария окна. `rows` — `rows_of`, `out` — `propose` по ним. Чистая функция.

    `boost_days` — дней до конца флайта ОТ СЕГОДНЯ (так считает окно буста, `boost.window`); `days_left` — от даты
    последнего факта (так считает темп). Они расходятся на сутки, и буст на `days_left` дней отказал бы."""
    names = lambda rs: ", ".join(r["name"] for r in rs)           # noqa: E731 — подпись списка площадок
    off = "РК окончена" if closed else ("флайт закончился" if days_left <= 0 else None)

    changed = {r["id"]: r["plan_new"] for r in out["rows"] if r.get("delta")}
    donors = [r for r in out["rows"] if r.get("role") == "донор"]
    takers = [r for r in out["rows"] if r.get("role") == "получатель"]
    move = {"key": "move", "title": "Перенести недобор на площадки в темпе", "moved": out.get("moved", 0),
            "unplaced": out.get("unplaced", 0), "plans": changed,
            "what": ((f"{names(donors)} отдаёт {out['moved']:,} показов → {len(takers)} площадкам в темпе"
                      + (f"; {out['unplaced']:,} не пристроить — запаса не хватает" if out.get("unplaced") else ""))
                     .replace(",", " ") if changed else "")}
    move["why_not"] = (off or (BOOST_LIVE if boost_live else None)
                       or (None if changed else "площадок, упёршихся в сеть, нет — переносить нечего"))

    # Буст не поднимает площадки с заданным объёмом — ни с ручным планом, ни с объёмом по креативам (`boost.boostable`)
    lag = [r for r in rows if r.get("running") and r.get("pace") == NOT_DELIVERED and r.get("fixed_plan") is None
           and not r.get("fixed")]
    pct = _lag_pct(lag, days_left) if lag and days_left > 0 else 0
    bdays = max(0, days_left if boost_days is None else boost_days)
    lagging = {"key": "lagging", "title": "Поднять темп не открутившим", "placement_ids": sorted(r["id"] for r in lag),
               "pct": pct, "days": bdays,
               "what": (f"{names(lag)}: трафик есть, показов меньше нужного — остаток +{pct} % до конца флайта ({bdays} дн.)"
                        if lag else ""),
               "confirm": f"Поднять темп: {names(lag)} — остаток +{pct} % на {bdays} дн. Лимиты сразу уйдут в DSP." if lag else "",
               "note": "заменит действующий «Поднять темп»" if lag and boost_live else None}
    live_txt = "уже идёт «Поднять темп» — его планы подняты, статусы площадок считаются от поднятых; снимите буст в окне «Поднять темп», чтобы пересчитать"
    lagging["why_not"] = (off or (None if lag else (live_txt if boost_live else "площадок «трафик есть, не открутили» без ручного плана нет"))
                          or (None if bdays > 0 else "флайт заканчивается сегодня — поднимать темп не на что"))

    dead = [r for r in rows if r.get("running") and r.get("pace") == NO_TRAFFIC and r.get("chronic")]
    drop = {"key": "drop", "title": "Снять площадки без трафика", "placement_ids": sorted(r["id"] for r in dead),
            "what": (f"{names(dead)} → «завершена»: план = факту, остаток разойдётся по долям" if dead else ""),
            "confirm": (f"Снять площадки без трафика: {names(dead)} → «завершена». План каждой = её факту, остаток разойдётся "
                        f"по долям, лимиты сразу уйдут в DSP." if dead else "")}
    drop["why_not"] = off or (None if dead else "площадок без трафика несколько суток подряд нет")

    reset = {"key": "reset", "title": "Сбросить ручные планы", "what": "площадки снова по долям (где задан объём по креативам — по нему)" if has_manual else "",
             # План РК урезали ниже ручных планов (26.10.2026): кнопка подсвечена, нажимает человек
             "urgent": bool(over_plan),
             "confirm": ("Снять записанные ручные планы — площадки снова по долям (где задан объём по креативам — по нему), "
                         "лимиты сразу уйдут в DSP.")}
    if over_plan:
        reset["what"] = (f"ручные планы {over_plan['manual']:,} больше плана РК {over_plan['plan']:,} — "
                         f"РК перекрутит; сброс вернёт площадки к долям (где задан объём по креативам — к нему)").replace(",", " ")
    reset["why_not"] = (off or (None if has_manual else "ручных планов нет"))

    out_list = [move, lagging, drop, reset]
    for s in out_list:
        s["enabled"] = s["why_not"] is None
        # Текст карточки — одним местом, здесь (владелец 26.10.2026): окно его только показывает
        s["text"] = s["what"] if s["enabled"] else s["why_not"]
    return out_list


# ── План РК урезали ниже ручных планов (владелец 26.10.2026): сначала уведомление, убирает человек кнопкой сброса ─────

def _over(manual: float, plan) -> bool:
    return bool(plan) and float(manual) > float(plan) * 1.001


def newly_over(manual: float, old_plan, new_plan) -> bool:
    """Сумма ручных планов стала больше плана РК ИМЕННО СЕЙЧАС — уведомить. Уже висящее превышение не шумит."""
    return bool(manual) and _over(manual, new_plan) and not _over(manual, old_plan)


def manual_sums(db, campaign_ids) -> dict:
    """{id РК: сумма ручных планов площадок в работе} — только РК, где они есть."""
    from sqlalchemy import text
    ids = list(campaign_ids)
    if not ids:
        return {}
    return {cid: float(s) for cid, s in db.execute(text(
        "SELECT campaign_id, sum(fixed_plan) FROM ad_campaign_placement "
        "WHERE campaign_id = ANY(:c) AND fixed_plan IS NOT NULL AND status = ANY(:w) GROUP BY campaign_id"),
        {"c": ids, "w": list(IN_WORK)}).all()}


def over_plan_of(db, camp) -> Optional[dict]:
    """{manual, plan} — если ручные планы РК в сумме больше её плана, иначе None (плашка окна)."""
    s = manual_sums(db, [camp.id]).get(camp.id, 0.0)
    return {"manual": round(s), "plan": round(camp.plan_show or 0)} if _over(s, camp.plan_show) else None


def alert_plan_cut(db, before: dict) -> list:
    """После обновления плана РК из медиаплана (`build.sync_campaigns`): `before` = {id РК: план до}. Где ручные планы
    впервые стали больше плана — уведомление трафику. Сами планы не трогаются: сбрасывает человек в окне (повторное
    согласие). Сбой уведомления сборку не роняет. → id РК, по которым ушло."""
    import logging
    from app.ad.models import AdCampaign
    from app.notify import bus
    from app.routers.traffic_dashboard import rk_label
    sent = []
    for cid, s in manual_sums(db, before).items():
        camp = db.get(AdCampaign, cid)
        if camp is None or not newly_over(s, before.get(cid), camp.plan_show):
            continue
        try:
            bus.emit(db, "traffic_manual_over_plan", title=f"Ручные планы больше плана РК: {rk_label(db, cid)}",
                     body=(f"План РК в медиаплане уменьшили до {round(camp.plan_show or 0):,}, а ручные планы площадок "
                           f"(«Перераспределить») в сумме {round(s):,}. РК перекрутит план — снимите ручные планы в окне "
                           f"«Темп размещения → Перераспределить» или перенесите заново.").replace(",", " "),
                     link=f"/traffic/dashboard?rk={cid}", entity_type="ad_campaign", entity_id=cid)
            sent.append(cid)
        except Exception:  # noqa: BLE001 — уведомление справка, сборка РК важнее
            logging.getLogger("finance.dsp").exception("уведомление о ручных планах РК %s не отправлено", cid)
    return sent


def daily_of(db, camp, as_of=None) -> dict:
    """Факт площадок РК по дням флайта (наш счётчик, как везде) — для графика «Динамика по дням» окна.
    → {"dates": [ISO дни флайта], "as_of": ISO, "facts": {id площадки: {ISO день: показы}}}"""
    from datetime import date, timedelta
    from sqlalchemy import text
    from app.ad.stat_sources import fact_as_of, fact_sources
    if not (camp.date_start and camp.date_end):
        return {"dates": [], "as_of": None, "facts": {}}
    as_of = as_of or fact_as_of(db, date.today())
    dates, d = [], camp.date_start
    while d <= camp.date_end:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    facts: dict = {}
    for r in db.execute(text("""SELECT placement_id, date, sum(shows) AS s FROM ad_campaign_stat
                                 WHERE campaign_id = :c AND placement_id IS NOT NULL AND date <= :u AND source = ANY(:src)
                                 GROUP BY placement_id, date"""),
                        {"c": camp.id, "u": as_of, "src": list(fact_sources())}).all():
        facts.setdefault(r.placement_id, {})[r.date.isoformat()] = int(r.s or 0)
    return {"dates": dates, "as_of": as_of.isoformat() if as_of else None, "facts": facts}


def journal_of(db, deal_id: int, limit: int = 20) -> List[dict]:
    from sqlalchemy import text
    rows = db.execute(text("""SELECT action, user_name, details, created_at FROM audit_log
                               WHERE entity_type = 'sales_deal' AND entity_id = :d
                                 AND action IN ('traffic_realloc', 'traffic_realloc_reset')
                               ORDER BY id DESC LIMIT :n"""), {"d": deal_id, "n": limit}).mappings().all()
    return history_of([dict(r) for r in rows])
