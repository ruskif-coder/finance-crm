# -*- coding: utf-8 -*-
"""Вкладка «Бизнес» экрана «Деньги» (владелец 20.11.2026): продано и в работе по месяцам — светофор продаж против учёта.

Правила (все решения владельца 20.11.2026):
- месяц сделки — месяц `period_from`; окно — прошлый месяц, текущий и три вперёд;
- слой — светофор продаж по НАШЕЙ стадии (`sales_stages.money_layer`): документы · в работе · планы; планы делятся по
  вероятности из разметки продаж (`sales.probability.effective`: бронь — средняя, раньше — низкая, если продажи не отметили);
- сумма — итоговая сверка, если подтверждена (`final_recon.closing.compute`, в ней «скидка в счёт» уже вычтена), иначе
  сумма МП, иначе сделки — за вычетом «скидки в счёт» (`final_recon.sk.modes_many`). СК постоплатой не вычитается: это расход;
- две ветви прогноза: «надёжно» = документы + в работе, «с вероятными» = + средняя вероятность;
- прошлый год — выручка из учёта за тот же месяц (операции со статьёй P&L «выручка», без НДС); план — цель «Плана продаж»
  (`sales_targets`, общая); целей нет — None, а не ноль;
- сверка прошлого месяца: «подкреплено документами» → выручка в учёте, шагами (счёта нет · сумма ≠ счёт · вне сделок).
Только чтение."""
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.final_recon.money import r2

LAYER = {"фактические": "docs", "реализуемые": "work", "планируемые": "plan"}
DISCOUNT = "скидка в счёт"
UNDER = 0.97                      # недокрут — прогноз ниже 97 % плана (тот же порог, что вердикт итоговой сверки)
MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


# ── чистые правила (тесты — без базы) ─────────────────────────────────────────────────────────────

def month_start(today: date, shift: int) -> date:
    """Первое число месяца, отстоящего от текущего на shift."""
    y, m = divmod(today.year * 12 + today.month - 1 + shift, 12)
    return date(y, m + 1, 1)


def month_keys(today: date) -> List[Tuple[str, str]]:
    """[(«ГГГГ-ММ», роль)]: прошлый месяц, текущий и три вперёд."""
    return [(month_start(today, s).strftime("%Y-%m"), "past" if s < 0 else "now" if s == 0 else "next") for s in range(-1, 4)]


def bucket(layer: Optional[str], light: Optional[str]) -> str:
    """Корзина светофора: docs | work | mid | low | lost. Без слоя — сорвавшаяся («не случились»)."""
    lay = LAYER.get(layer or "")
    if lay is None:
        return "lost"
    if lay != "plan":
        return lay
    return "low" if light == "grey" else "mid"      # «факт» на стадии планов продажи ставят как уверенность — это вероятные


def net_of_discount(amount: float, mode: Optional[str], pct: Optional[float]) -> float:
    """Сумма, которая придёт к нам: минус «скидка в счёт». Постоплата и неизвестный способ — без вычета."""
    if mode == DISCOUNT and pct:
        return r2(amount * (1 - float(pct) / 100))
    return r2(amount)


def money_in_flight(amount: float, plan: Optional[float], fact: Optional[float], forecast: Optional[float]) -> Tuple[Optional[float], float]:
    """(открутилось в деньгах | None, под риском недокрута). Нет плана показов — открутку не знаем."""
    if not plan:
        return None, 0.0
    done = r2(amount * min((fact or 0) / plan, 1.0))
    risk = r2(amount * (plan - forecast) / plan) if (forecast is not None and forecast < UNDER * plan) else 0.0
    return done, risk


def recon_steps(docs: Dict[int, float], shares: Dict[int, float], outside: float) -> dict:
    """Сверка «подкреплено документами» → учёт. docs — {сделка: сумма светофора}, shares — {сделка: её доля в выручке месяца}
    (по всем сделкам, куда ушла выручка), outside — выручка месяца, не дошедшая ни до одной сделки месяца в документах.
    Тождество: from + Σ шагов = to."""
    no_bill = {d: a for d, a in docs.items() if d not in shares}
    diffs = {d: r2(shares[d] - a) for d, a in docs.items() if d in shares}
    elsewhere = r2(outside + sum(v for d, v in shares.items() if d not in docs))
    frm = r2(sum(docs.values()))
    steps = [{"key": "no_bill", "v": -r2(sum(no_bill.values())), "deals": sorted(no_bill, key=lambda d: -no_bill[d])},
             {"key": "diff", "v": r2(sum(diffs.values())), "deals": sorted((d for d in diffs if abs(diffs[d]) >= 1000), key=lambda d: -abs(diffs[d]))},
             {"key": "outside", "v": elsewhere, "deals": []}]
    return {"from": frm, "to": r2(frm + sum(s["v"] for s in steps)), "steps": steps, "diffs": diffs}


# ── данные ────────────────────────────────────────────────────────────────────────────────────────

def _deals(db: Session, first: date, last: date) -> list:
    from app.sales.models import SalesDeal
    rows = db.execute(text("""
        SELECT d.id, s.money_layer, s.stage_key, s.name AS stage, coalesce(sv.name, 'без услуги') AS service
          FROM sales_deals d LEFT JOIN sales_stages s ON s.id = d.our_stage_id LEFT JOIN sales_services sv ON sv.id = d.service_id
         WHERE d.period_from >= :a AND d.period_from <= :b"""), {"a": first, "b": last}).mappings().all()
    meta = {r["id"]: r for r in rows}
    objs = db.query(SalesDeal).filter(SalesDeal.id.in_(list(meta) or [0])).all()
    return [(d, meta[d.id]) for d in objs]


def _confirmed(db: Session, ids: Iterable[int]) -> set:
    ids = list(ids)
    if not ids:
        return set()
    return {r[0] for r in db.execute(text("SELECT deal_id FROM final_recon_deals WHERE deal_id = ANY(:i) AND confirmed_at IS NOT NULL"),
                                     {"i": ids})}


def amounts(db: Session, deals: list, memo: dict) -> Dict[int, float]:
    """{сделка: сумма светофора} — сверка, иначе МП/сделка за вычетом «скидки в счёт»."""
    from app.final_recon import closing as CL
    from app.final_recon import sk as SK
    from app.sales import mp_amounts as MA
    objs = [d for d, _ in deals]
    mp = MA.mp_amounts_by_deal(db, [d.id for d in objs])
    modes = SK.modes_many(db, objs)
    done = _confirmed(db, [d.id for d in objs])
    out = {}
    for d in objs:
        if d.id in done:
            if d.id not in memo:
                memo[d.id] = CL.compute(db, d)
            out[d.id] = r2(memo[d.id].get("total_net") or 0)
        else:
            mode, pct = modes.get(d.id, (None, None))
            out[d.id] = net_of_discount(MA.eff_net(d, mp), mode, pct)
    return out


def revenue_by_month(db: Session, keys: List[str]) -> Dict[str, float]:
    """Выручка учёта без НДС по месяцам периода; квартальная операция — третью на каждый свой месяц."""
    from app.periods import quarter_parts
    rows = db.execute(text("""SELECT o.period, sum(o.income - coalesce(o.vat_fact, 0)) FROM operations o JOIN articles a ON a.id = o.article_id
                               WHERE a.pl_line = 'revenue' GROUP BY o.period""")).all()
    out = defaultdict(float)
    for period, v in rows:
        p = (period or "").strip()
        if p in keys:
            out[p] += float(v or 0)
            continue
        q = quarter_parts(p)
        if q:
            yq = [k for k in keys if k[:4] == q[0][:4] and q[0] <= k <= q[1]]
            for k in yq:
                out[k] += float(v or 0) / 3
    return {k: r2(out.get(k, 0)) for k in keys}


def _ly_key(k: str) -> str:
    return f"{int(k[:4]) - 1:04d}{k[4:]}"


def targets(db: Session, keys: List[str]) -> Dict[str, Optional[float]]:
    rows = {(int(y), int(m)): float(a) for y, m, a in db.execute(text("SELECT year, month, amount FROM sales_targets WHERE scope = 'общий'"))}
    return {k: rows.get((int(k[:4]), int(k[5:]))) for k in keys}


def _deal_ops(db: Session, month: Optional[str] = None) -> Tuple[Dict[int, float], float, set]:
    """Выручка операций → сделки через мост (операция → комплект → ДС → доли сделок по разнесению ДС).
    month — только операции этого периода; → ({сделка: доля без НДС}, выручка без сделки, сделки с операцией)."""
    q = """SELECT o.id, o.income - coalesce(o.vat_fact, 0) AS net, k.annex_id FROM operations o JOIN articles a ON a.id = o.article_id
             LEFT JOIN master_deal_upds k ON k.id = o.master_deal_upd_id
            WHERE a.pl_line = 'revenue' AND coalesce(o.income, 0) > 0""" + (" AND o.period = :m" if month else "")
    ops = db.execute(text(q), {"m": month}).mappings().all()
    alloc = defaultdict(list)
    for r in db.execute(text("SELECT annex_id, deal_id, coalesce(amount, 0) FROM sales_deal_annex_allocation")):
        alloc[r[0]].append((r[1], float(r[2])))
    shares, outside = defaultdict(float), 0.0
    for o in ops:
        parts = alloc.get(o["annex_id"]) or []
        if not parts:
            outside += float(o["net"] or 0)
            continue
        tot = sum(a for _, a in parts)
        for did, a in parts:
            shares[did] += float(o["net"] or 0) * (a / tot if tot else 1 / len(parts))
    return {d: r2(v) for d, v in shares.items()}, r2(outside), set(shares)


def _invoiced(db: Session, ids: Iterable[int]) -> set:
    """Сделки, по чьему комплекту 1С уже вернула номер счёта (разнесение ДС → комплект УПД с `onec_invoice_no`)."""
    ids = list(ids)
    if not ids:
        return set()
    return {r[0] for r in db.execute(text("""SELECT DISTINCT x.deal_id FROM sales_deal_annex_allocation x
                                               JOIN master_deal_upds k ON k.annex_id = x.annex_id
                                              WHERE x.deal_id = ANY(:i) AND k.onec_invoice_no IS NOT NULL"""), {"i": ids})}


def _packages(db: Session, ids: Iterable[int]) -> dict:
    ids = list(ids)
    if not ids:
        return {}
    return {r.deal_id: r for r in db.execute(text("""SELECT i.deal_id, m.code, m.status, m.updated_at FROM master_deal_items i
                                                        JOIN master_deals m ON m.id = i.master_deal_id WHERE i.deal_id = ANY(:i)"""), {"i": ids})}


def _placement(db: Session, deals: list, amt: Dict[int, float]) -> dict:
    """Деньги в размещении — слой «в работе» текущего месяца, с откруткой РК (показы к плану, прогноз — как дашборд трафика)."""
    from app.ad.flight import flight_of, forecast_of
    from app.ad.stat_sources import fact_as_of
    from app.traffic.delivery_facts import _facts
    ids = [d.id for d, _ in deals]
    camps = defaultdict(list)
    for r in db.execute(text("SELECT id, deal_id, plan_show, date_start, date_end FROM ad_campaign WHERE deal_id = ANY(:i)"), {"i": ids or [0]}).mappings():
        camps[r["deal_id"]].append(r)
    facts = _facts(db, [c["id"] for cs in camps.values() for c in cs])
    as_of = fact_as_of(db)
    total = done = risk = 0.0
    risk_n = no_rk = 0
    by_svc = defaultdict(lambda: [0.0, 0])
    for d, meta in deals:
        a = amt.get(d.id, 0.0)
        total += a
        by_svc[meta["service"]][0] += a
        by_svc[meta["service"]][1] += 1
        cs = camps.get(d.id) or []
        plan = sum(float(c["plan_show"] or 0) for c in cs)
        fact = sum(float((facts.get(c["id"]) or {}).get("shows") or 0) for c in cs)
        starts = [c["date_start"] for c in cs if c["date_start"]]
        ends = [c["date_end"] for c in cs if c["date_end"]]
        fl = flight_of(min(starts), max(ends), as_of) if starts and ends else None
        got, r = money_in_flight(a, plan, fact, forecast_of(plan, fact, fl))
        if got is None:
            no_rk += 1
            continue
        done += got
        risk += r
        risk_n += 1 if r > 0 else 0
    return {"total": r2(total), "deals": len(deals), "delivered": r2(done), "delivered_pct": round(done / total * 100) if total else None,
            "at_risk": r2(risk), "at_risk_deals": risk_n, "no_rk": no_rk, "as_of": as_of.isoformat() if as_of else None,
            "by_service": sorted(([s, r2(v[0]), v[1]] for s, v in by_svc.items()), key=lambda x: -x[1])}


def _margin(db: Session, deals: list, memo: dict) -> dict:
    """Прямая маржа по услугам — сделки с подтверждённой итоговой сверкой (правило `master_deal.efficiency.row`)."""
    from app.final_recon import closing as CL
    from app.master_deal import efficiency as EF
    done = _confirmed(db, [d.id for d, _ in deals])
    grp = defaultdict(list)
    for d, meta in deals:
        if d.id not in done:
            continue
        if d.id not in memo:
            memo[d.id] = CL.compute(db, d)
        grp[meta["service"]].append(EF.row(d.code, memo[d.id], EF.estimate(db, d.id)))
    rows = []
    for svc, rs in grp.items():
        known = [r for r in rs if r["cost"] is not None]       # без себестоимости сделка в маржу не идёт — охват виден отдельно
        t = EF.total(known) if known else None
        rows.append({"service": svc, "deals": len(rs), "with_cost": len(known), "revenue": t["revenue"] if t else 0.0,
                     "gross": t["gross"] if t else 0.0, "cost": t["cost"] if t else None, "sk_cost": t["sk_cost"] if t else 0.0,
                     "profit": t["profit"] if t else None, "margin_pct": t["margin_pct"] if t else None,
                     "estimated": len(t["estimated"]) if t else 0, "revenue_all": r2(sum(r["revenue"] for r in rs))})
    return {"rows": sorted(rows, key=lambda r: -r["revenue_all"]), "deals": sum(r["deals"] for r in rows)}


def speed(db: Session, today: date) -> dict:
    """Скорость денег за 90 дней («Путь денег», хендофф 20.11.2026): средние дни от конца флайта до счёта 1С и от счёта до
    оплаты, рядом — средняя отсрочка тех же контрагентов (`term_days`, иначе 60 — правило дебиторки). Нет данных — None."""
    from app.receivables import DEFAULT_TERM_DAYS
    since = today - timedelta(days=90)
    to_inv = db.execute(text("""SELECT avg(k.onec_invoice_date - d.period_to)::float FROM master_deal_upds k
                                  JOIN sales_deal_annex_allocation x ON x.annex_id = k.annex_id JOIN sales_deals d ON d.id = x.deal_id
                                 WHERE k.onec_invoice_date >= :s AND d.period_to IS NOT NULL"""), {"s": since}).scalar()
    pay = db.execute(text("""SELECT avg(o.date - o.invoice_date)::float, avg(coalesce(c.term_days, :t))::float, count(*)
                               FROM operations o LEFT JOIN counterparties c ON c.id = o.counterparty_id
                              WHERE o.status = 'ОПЛАЧЕНО' AND coalesce(o.income, 0) > 0 AND o.invoice_date IS NOT NULL
                                AND o.date >= :s AND o.date >= o.invoice_date"""), {"s": since, "t": DEFAULT_TERM_DAYS}).first()
    return {"to_invoice_days": round(to_inv) if to_inv is not None else None,
            "to_pay_days": round(pay[0]) if pay and pay[0] is not None else None,
            "term_days": round(pay[1]) if pay and pay[1] is not None else None, "paid_n": int(pay[2]) if pay else 0}


def _row(d, meta, a: float) -> dict:
    return {"code": d.code, "title": d.title, "service": meta["service"], "stage": meta["stage"], "amount": a}


def build(db: Session, today: date) -> dict:
    from app.sales import probability as P
    keys = month_keys(today)
    ks = [k for k, _ in keys]
    last = month_start(today, 4) - timedelta(days=1)
    back = month_start(today, -3)          # «счёта нет» и маржа — ещё два месяца до прошлого
    memo: dict = {}
    window = _deals(db, back, last)
    amt = amounts(db, window, memo)
    ly = revenue_by_month(db, [_ly_key(k) for k in ks])
    plan = targets(db, ks)
    months = {k: {"key": k, "name": MONTHS_NOM[int(k[5:]) - 1], "role": role, "docs": 0.0, "work": 0.0, "mid": 0.0, "low": 0.0, "lost": 0.0,
                  "ly": ly[_ly_key(k)], "plan": plan[k], "deals": {"docs": [], "work": [], "mid": [], "low": [], "lost": []}} for k, role in keys}
    per = {}
    for d, meta in window:
        b = bucket(meta["money_layer"], P.effective(d.probability_color, meta["stage_key"], lost=not meta["money_layer"]))
        per[d.id] = b
        k = d.period_from.strftime("%Y-%m")
        if k in months:
            months[k][b] = r2(months[k][b] + amt[d.id])
            months[k]["deals"][b].append(_row(d, meta, amt[d.id]))
    for mo in months.values():
        for lst in mo["deals"].values():
            lst.sort(key=lambda r: -r["amount"])

    # «сделано, а счёта нет» — документы прошлых месяцев в пакете закрытия, по комплекту которых 1С ещё не дала счёт.
    # Сделки без пакета (закрывались вне системы — до мастер-сделок) — отдельной строкой: про их счёт система не знает.
    past_docs = [(d, meta) for d, meta in window if per[d.id] == "docs" and d.period_from.strftime("%Y-%m") < ks[1]]
    pk = _packages(db, [d.id for d, _ in past_docs])
    billed = _invoiced(db, [d.id for d, _ in past_docs])
    unbilled, outside_sys = [], []
    for d, meta in past_docs:
        if d.id in billed:
            continue
        p = pk.get(d.id)
        if p is None and d.period_from.strftime("%Y-%m") != ks[0]:
            outside_sys.append(amt[d.id])           # старше прошлого месяца без пакета — хвост «вне пакетов»
            continue
        unbilled.append({**_row(d, meta, amt[d.id]), "month": MONTHS_NOM[d.period_from.month - 1].lower(),
                         "package": p.code if p else None, "package_status": p.status if p else None,     # нет пакета — «есть в сверке»
                         "since": p.updated_at.date().isoformat() if p and p.updated_at else None,
                         "days": (today - p.updated_at.date()).days if p and p.updated_at else None})
    unbilled.sort(key=lambda r: -r["amount"])

    # сверка прошлого месяца
    pm = ks[0]
    docs_pm = {d.id: amt[d.id] for d, _ in window if per[d.id] == "docs" and d.period_from.strftime("%Y-%m") == pm}
    shares, outside, _ = _deal_ops(db, month=pm)
    rc = recon_steps(docs_pm, shares, outside)
    code = {d.id: d.code for d, _ in window}
    for s in rc["steps"]:
        s["items"] = [{"code": code.get(i, f"#{i}"), "v": (-docs_pm[i] if s["key"] == "no_bill" else rc["diffs"][i])} for i in s.pop("deals")[:8]]
    rc.pop("diffs")

    now_work = [(d, meta) for d, meta in window if per[d.id] == "work" and d.period_from.strftime("%Y-%m") == ks[1]]
    closed = [(d, meta) for d, meta in window if d.period_from.strftime("%Y-%m") < ks[1]]
    return {"today": today.isoformat(), "months": list(months.values()), "placement": _placement(db, now_work, amt),
            "unbilled": {"total": r2(sum(r["amount"] for r in unbilled)), "rows": unbilled,
                         "outside": {"deals": len(outside_sys), "total": r2(sum(outside_sys))}},
            "recon": {"month": MONTHS_NOM[int(pm[5:]) - 1].lower(), "key": pm, **rc},
            "speed": speed(db, today),
            "margin": {"months": [k for k in sorted({d.period_from.strftime('%Y-%m') for d, _ in closed})], **_margin(db, closed, memo)}}
