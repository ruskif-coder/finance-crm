# -*- coding: utf-8 -*-
"""Расчёт СК за месяц и квартал и закрытый месяц (владелец 27.10.2026, docs/СХЕМА_СК.md).

* В расчёт идут ЗАКРЫТЫЕ сделки — их мастер-сделка прошла согласования в ДО (статус «ждём 1С» и дальше). Остальные
  сделки месяца — списком «не закрыта» с оценкой по сумме сделки, в итог не входят.
* База — сумма ДС без НДС до вычета скидки: тот же расчёт, что ДС (`final_recon.closing`). Основная СК — тоже оттуда
  (`final_recon.sk.of_deal`: поправка на сделке, иначе правило), так что расчёт и ДС не расходятся.
* Партнёрская — отдельные выплаты: самое точное правило на каждого получателя (`rules.pick_partners`).
* Открытый месяц считается на лету; «Закрыть месяц» пишет снимок `sk_accruals`, дальше месяц читается из него.
  Сделка, закрытая после закрытия своего месяца, попадает в ближайший открытый."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agency_terms import rules as R
from app.agency_terms.models import SkAccrual, SkMonth


class CalcError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def months(period: str) -> List[str]:
    try:
        return R.months_of(period)
    except R.RuleError as e:
        raise CalcError(400, str(e))


def _r2(v) -> Optional[float]:
    return round(float(v), 2) if v is not None else None


def _done_statuses() -> list:
    from app.master_deal.status import STATUSES, WAIT_1C
    return list(STATUSES[STATUSES.index(WAIT_1C):])


def _closed_months(db: Session) -> dict:
    return {p: at for p, at in db.execute(text("SELECT period, closed_at FROM sk_months")).all()}


_DEALS_ANY = """
    SELECT d.id, d.code, d.title, to_char(d.period_from, 'YYYY-MM') AS period, d.amount,
           d.agency_id, d.advertiser_id, d.brand_id, d.service_id, d.ord_final_contract_id AS contract_id,
           coalesce(a.short_name, a.name) AS agency, coalesce(adv.short_name, adv.name) AS advertiser,
           b.name AS brand, s.name AS service,
           c.contract_number, c.contract_date, c.counterparty_id AS entity_id, coalesce(cp.name, c.counterparty_name) AS entity,
           m.id AS master_id, m.code AS master_code, m.status AS master_status
      FROM sales_deals d
      LEFT JOIN sales_stages st ON st.id = d.our_stage_id
      LEFT JOIN sales_agencies a ON a.id = d.agency_id
      LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
      LEFT JOIN sales_brands b ON b.id = d.brand_id
      LEFT JOIN sales_services s ON s.id = d.service_id
      LEFT JOIN contracts c ON c.id = d.ord_final_contract_id
      LEFT JOIN counterparties cp ON cp.id = c.counterparty_id
      LEFT JOIN master_deal_items i ON i.deal_id = d.id
      LEFT JOIN master_deals m ON m.id = i.master_deal_id"""
# Живой расчёт — без проигранных; снимок закрытого месяца — все начисленные, даже проигранные позже (ревью 27.10.2026)
_DEALS = _DEALS_ANY + " WHERE coalesce(st.is_lost, false) = false"


def _head(r: dict) -> dict:
    side = r["agency"] if r["agency_id"] else f"{r['advertiser'] or '—'} (прямой)"
    num = r["contract_number"] or "без договора"
    if r["contract_date"]:
        num = f"{num} от {r['contract_date'].strftime('%d.%m.%Y')}"
    return {"deal_id": r["id"], "code": r["code"], "title": r["title"], "deal_period": r["period"],
            "side": side, "agency_id": r["agency_id"], "advertiser_id": r["advertiser_id"], "brand_id": r["brand_id"],
            "advertiser": r["advertiser"], "brand": r["brand"], "service": r["service"],
            "entity": r["entity"] or "—", "entity_id": r["entity_id"], "contract": num, "contract_id": r["contract_id"],
            "master_id": r["master_id"], "master_code": r["master_code"]}


def _live_row(db: Session, r: dict, rules: list) -> dict:
    from app.final_recon import closing as CL
    from app.final_recon import sk as SK
    from app.sales.models import SalesDeal
    deal = db.get(SalesDeal, r["id"])
    out = CL.compute(db, deal)
    base = _r2((out["base_ds_net"] or 0) + (out["paid_extras_net"] or 0)) if out["base_ds_net"] is not None else None
    sk = out["sk"]
    on = R.close_date(r["period"])
    partners = []
    for p in R.pick_partners(rules, SK.features_of(deal), on):
        partners.append({"rule_id": p["id"], "recipient_id": p["recipient_id"], "mode": p["mode"], "percent": p["percent"],
                         "amount": _r2((base or 0) * p["percent"] / 100.0)})
    return {**_head(r), "base_net": base,
            "main": {"rule_id": sk.get("rule_id"), "mode": sk["mode"], "percent": sk["percent"], "source": sk["source"],
                     "amount": _r2(sk.get("amount_net")) if sk["mode"] else None},
            "partners": partners}


def _names(db: Session, ids) -> dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return dict(db.execute(text("SELECT id, name FROM counterparties WHERE id = ANY(:i)"), {"i": ids}).all())


def _live(db: Session, period: str, closed: dict) -> dict:
    """Открытый месяц: закрытые сделки этого месяца и «опоздавшие» из уже закрытых месяцев; прочие сделки месяца — «не закрыта»."""
    from app.final_recon import closing as CL
    from app.final_recon import sk as SK
    done = _done_statuses()
    accrued = {d for (d,) in db.execute(text("SELECT DISTINCT deal_id FROM sk_accruals")).all()}
    raw = [dict(r) for r in db.execute(text(_DEALS + " AND to_char(d.period_from, 'YYYY-MM') <= :p ORDER BY d.code"),
                                       {"p": period}).mappings().all()]
    rows, open_rows = [], []
    rules = SK._rules(db)
    with CL.memo(db):
        for r in raw:
            is_closed = r["master_status"] in done
            if r["period"] == period and not is_closed:
                rule = R.pick(rules, {k: r[k] for k in R.FEATURES}, R.close_date(period), R.MAIN)
                open_rows.append({**_head(r), "estimate_net": _r2(r["amount"]), "master_status": r["master_status"],
                                  "percent": rule["percent"] if rule else None, "mode": rule["mode"] if rule else None})
                continue
            late = r["period"] < period and r["period"] in closed and late_home(r["period"], closed) == period
            if is_closed and r["id"] not in accrued and (r["period"] == period or late):
                rows.append({**_live_row(db, r, rules), "late": late})
    names = _names(db, [p["recipient_id"] for x in rows for p in x["partners"]])
    for x in rows:
        for p in x["partners"]:
            p["recipient"] = names.get(p["recipient_id"])
    return {"rows": rows, "open": open_rows}


def _snapshot(db: Session, period: str) -> list:
    acc = db.query(SkAccrual).filter(SkAccrual.period == period).all()
    ids = sorted({a.deal_id for a in acc})
    heads = {r["id"]: _head(dict(r)) for r in db.execute(text(_DEALS_ANY + " WHERE d.id = ANY(:i)"), {"i": ids or [0]}).mappings()}
    names = _names(db, [a.recipient_id for a in acc])
    by: dict = {}
    for a in acc:
        row = by.setdefault(a.deal_id, {**heads.get(a.deal_id, {"deal_id": a.deal_id}), "base_net": _r2(a.base_net),
                                        "main": {"mode": None, "percent": None, "amount": None, "rule_id": None,
                                                 "source": "none"}, "partners": []})
        part = {"rule_id": a.rule_id, "mode": a.mode, "percent": _r2(a.percent), "amount": _r2(a.amount_net)}
        if a.kind == R.MAIN:
            row["main"] = {**part, "source": "rule" if a.rule_id else ("deal" if a.mode else "none")}
        else:
            row["partners"].append({**part, "recipient_id": a.recipient_id, "recipient": names.get(a.recipient_id)})
    return [by[d] for d in ids]


def month_rows(db: Session, period: str) -> dict:
    closed = _closed_months(db)
    if period in closed:
        return {"period": period, "closed": True, "closed_at": closed[period].isoformat(), "rows": _snapshot(db, period),
                "open": []}
    return {"period": period, "closed": False, "closed_at": None, **_live(db, period, closed)}


def close_month(db: Session, period: str, user) -> int:
    """Снимок месяца. Отказ: уже закрыт; есть закрытые сделки без условия (СК не посчитать). → число строк снимка."""
    months(period)
    if len(period) != 7:
        raise CalcError(400, "Закрывается месяц, не квартал")
    if db.get(SkMonth, period):
        raise CalcError(409, f"Месяц {period} уже закрыт")
    live = _live(db, period, _closed_months(db))
    missing = [r["code"] for r in live["rows"] if r["main"]["source"] == "none" or r["base_net"] is None]
    if missing:
        more = f" и ещё {len(missing) - 8}" if len(missing) > 8 else ""
        raise CalcError(409, f"Не задано условие СК или нет суммы ДС: {', '.join(missing[:8])}{more} — задайте условие и закройте снова")
    db.add(SkMonth(period=period, closed_by=getattr(user, "id", None), closed_at=datetime.utcnow()))
    db.flush()
    n = 0
    for r in live["rows"]:
        m = r["main"]
        db.add(SkAccrual(period=period, deal_id=r["deal_id"], master_deal_id=r["master_id"], kind=R.MAIN,
                         rule_id=m["rule_id"], mode=m["mode"], percent=m["percent"], base_net=r["base_net"],
                         amount_net=m["amount"]))
        n += 1
        for p in r["partners"]:
            db.add(SkAccrual(period=period, deal_id=r["deal_id"], master_deal_id=r["master_id"], kind=R.PARTNER,
                             rule_id=p["rule_id"], recipient_id=p["recipient_id"], mode=p["mode"], percent=p["percent"],
                             base_net=r["base_net"], amount_net=p["amount"]))
            n += 1
    db.flush()
    return n


def reopen_month(db: Session, period: str) -> None:
    m = db.get(SkMonth, period)
    if m is None:
        raise CalcError(404, f"Месяц {period} не закрыт")
    db.delete(m)                # снимок уходит каскадом
    db.flush()


# ── свёртка (чистые функции) ────────────────────────────────────────────────────────────────────────

def _sum(rows, key) -> float:
    return round(sum(float(x.get(key) or 0) for x in rows), 2)


def _main_amount(rows) -> float:
    return round(sum(float(x["main"].get("amount") or 0) for x in rows), 2)


def tree(rows: List[dict]) -> List[dict]:
    """Агентство (рекламодатель при прямом договоре) → юрлицо → договор → сделки, с суммами на каждом уровне."""
    sides: dict = {}
    for r in rows:
        s = sides.setdefault(r["side"], {})
        e = s.setdefault(r["entity"], {})
        e.setdefault(r["contract"], []).append(r)
    out = []
    for sname in sorted(sides):
        ents = []
        for ename in sorted(sides[sname]):
            cons = [{"name": c, "deals": ds, "base_net": _sum(ds, "base_net"), "main_amount": _main_amount(ds)}
                    for c, ds in sorted(sides[sname][ename].items())]
            flat = [d for c in cons for d in c["deals"]]
            ents.append({"name": ename, "contracts": cons, "base_net": _sum(flat, "base_net"), "main_amount": _main_amount(flat)})
        flat = [d for e in ents for c in e["contracts"] for d in c["deals"]]
        out.append({"name": sname, "entities": ents, "base_net": _sum(flat, "base_net"), "main_amount": _main_amount(flat)})
    return out


def totals(rows: List[dict]) -> dict:
    by_mode: dict = {}
    partners: dict = {}
    for r in rows:
        m = r["main"]
        if m.get("mode"):
            by_mode[m["mode"]] = round(by_mode.get(m["mode"], 0) + float(m.get("amount") or 0), 2)
        for p in r["partners"]:
            k = p["recipient_id"]
            partners.setdefault(k, {"recipient_id": k, "recipient": p.get("recipient"), "amount": 0.0})
            partners[k]["amount"] = round(partners[k]["amount"] + float(p.get("amount") or 0), 2)
    return {"base_net": _sum(rows, "base_net"), "by_mode": by_mode,
            "no_rule": sum(1 for r in rows if r["main"].get("source") == "none"),
            "partners": sorted(partners.values(), key=lambda x: x["recipient"] or "")}


FILTERS = ("agency_id", "advertiser_id", "entity_id", "contract_id", "mode")


def _passes(r: dict, f: dict) -> bool:
    for k, v in f.items():
        if v in (None, ""):
            continue
        if k == "mode":
            if v == "не задано" and r["main"].get("mode"):
                return False
            if v != "не задано" and r["main"].get("mode") != v:
                return False
        elif str(r.get(k)) != str(v):
            return False
    return True


def calc(db: Session, period: str, filters: Optional[dict] = None, with_partners: bool = False) -> dict:
    """Месяц или квартал: строки сделок, дерево, итоги, «не закрыта», состояние месяцев. Партнёрская (`with_partners`) —
    только для вкладки спец. условий (хендофф 27.10.2026): у основного расчёта её суммы вырезаются."""
    ms = months(period)
    f = {k: v for k, v in (filters or {}).items() if k in FILTERS}
    rows, open_rows, state = [], [], []
    for p in ms:
        m = month_rows(db, p)
        state.append({"period": p, "closed": m["closed"], "closed_at": m["closed_at"]})
        rows += [{**r, "period": p} for r in m["rows"] if _passes(r, f)]
        open_rows += [{**r, "period": p} for r in m["open"] if _passes({**r, "main": {"mode": r.get("mode")}}, f)]
    if not with_partners:
        rows = [{**r, "partners": []} for r in rows]
    return {"period": period, "months": state, "rows": rows, "tree": tree(rows), "totals": totals(rows), "open": open_rows}


def late_home(deal_period: str, closed) -> str:
    """Месяц расчёта сделки, прошедшей ДО после закрытия своего месяца: первый незакрытый месяц после него. Ровно один —
    иначе квартал и обороты спец. условий считали бы её в каждом открытом месяце (ревью 27.10.2026)."""
    y, m = int(deal_period[:4]), int(deal_period[5:7])
    while True:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        cur = f"{y}-{m:02d}"
        if cur not in closed:
            return cur
