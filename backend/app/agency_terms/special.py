# -*- coding: utf-8 -*-
"""Расчёт спец. условий и партнёрской СК (хендофф 27.10.2026, решения владельца). Скрытая вкладка, право `sk_special`.

* % без порога — с оборота объекта за месяц.
* % с порогом («3 % при обороте от 30 млн за год») — пока оборот года нарастающим не дошёл до порога, «копится»; в месяце
  прохождения начисляется % со ВСЕГО оборота года задним числом, дальше — с оборота каждого месяца.
* Фикс — равными долями по месяцам срока (дата «по» у фикса обязательна).
* Оборот — сумма ДС без НДС закрытых сделок объекта привязки (договор / агентство / рекламодатель / бренд) по месяцам
  расчёта СК (`calc.month_rows`: закрытый месяц — из снимка), только внутри срока условия.
* Партнёрская — отдельные выплаты получателям: те же строки расчёта, что считает основная СК при закрытии месяца.
Квартал — сумма месяцев. Ядро (`accrue`, `in_scope`) — чистые функции."""
import calendar
from datetime import date
from typing import Dict, List

SCOPE_FIELD = {"договор": "contract_id", "агентство": "agency_id", "рекламодатель": "advertiser_id", "бренд": "brand_id"}


def _r2(v) -> float:
    return round(float(v or 0), 2)


def in_scope(term: dict, row: dict) -> bool:
    return row.get(SCOPE_FIELD.get(term["scope_kind"], "")) == term["scope_id"]


def _bounds(m: str):
    y, mm = int(m[:4]), int(m[5:7])
    return date(y, mm, 1), date(y, mm, calendar.monthrange(y, mm)[1])


def covers(term: dict, m: str) -> bool:
    first, last = _bounds(m)
    return term["valid_from"] <= last and (term.get("valid_to") is None or term["valid_to"] >= first)


def term_months(term: dict) -> List[str]:
    """Месяцы срока условия (для фикса — на сколько долей делить)."""
    if term.get("valid_to") is None:
        return []
    out, y, m = [], term["valid_from"].year, term["valid_from"].month
    while (y, m) <= (term["valid_to"].year, term["valid_to"].month):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _month_accrual(term: dict, turn: Dict[str, float], m: str) -> dict:
    if not covers(term, m):
        return {"accrued": 0.0, "active": False, "ytd": None}
    if term.get("amount") is not None and term.get("percent") is None:
        months = term_months(term)
        return {"accrued": _r2(float(term["amount"]) / len(months)) if months else 0.0, "active": True, "ytd": None}
    pct = float(term.get("percent") or 0) / 100.0
    t = float(turn.get(m) or 0)
    thr = term.get("threshold")
    if thr is None:
        return {"accrued": _r2(t * pct), "active": True, "ytd": None}
    before = sum(float(v or 0) for k, v in turn.items() if k[:4] == m[:4] and k < m and covers(term, k))
    ytd = before + t
    if before >= float(thr):
        acc = t * pct                       # порог пройден раньше — с оборота месяца
    elif ytd >= float(thr):
        acc = ytd * pct                     # порог пройден в этом месяце — со всего оборота года задним числом
    else:
        acc = 0.0                           # копится
    return {"accrued": _r2(acc), "active": True, "ytd": ytd}


def accrue(term: dict, turn: Dict[str, float], months: List[str]) -> dict:
    """Начисление условия за месяцы периода: сумма, база (оборот периода), оборот года нарастающим, статус, доля фикса."""
    parts = [_month_accrual(term, turn, m) for m in months]
    accrued = _r2(sum(p["accrued"] for p in parts))
    active = any(p["active"] for p in parts)
    ytd = next((p["ytd"] for p in reversed(parts) if p["ytd"] is not None), None)
    fix = term.get("amount") is not None and term.get("percent") is None
    if not active:
        status = "не действует"
    elif term.get("threshold") is not None and ytd is not None and ytd < float(term["threshold"]):
        status = "копится"
    else:
        status = "начислено"
    out = {"accrued": accrued, "status": status, "ytd": _r2(ytd) if ytd is not None else None,
           "base": None if fix else _r2(sum(float(turn.get(m) or 0) for m in months if covers(term, m)))}
    if fix:
        tm = term_months(term)
        last = months[-1]
        out["months"] = len(tm)
        out["month_no"] = (tm.index(last) + 1) if last in tm else (len(tm) if tm and last > tm[-1] else 0)
    return out


# ── по базе ──────────────────────────────────────────────────────────────────────────────────────────

def calc_special(db, period: str) -> dict:
    """Вкладка «Спец. условия»: начисления спец. условий и выплаты партнёрской за месяц или квартал, KPI «начислено»,
    «копится до порога», «с начала года». Оборот — по месяцам расчёта СК с января года периода."""
    from app.agency_terms import calc as C
    from app.agency_terms.models import SkSpecialTerm
    from app.agency_terms.service import special_dict
    months = C.months(period)
    year = months[0][:4]
    upto = [f"{year}-{m:02d}" for m in range(1, int(months[-1][5:7]) + 1)]
    rows_by = {m: C.month_rows(db, m)["rows"] for m in upto}
    items = []
    for t in (special_dict(s) for s in db.query(SkSpecialTerm).order_by(SkSpecialTerm.id).all()):
        turn = {m: sum(float(r.get("base_net") or 0) for r in rows if in_scope(t, r)) for m, rows in rows_by.items()}
        got = accrue(t, turn, months)
        year_acc = accrue(t, turn, upto)["accrued"]
        items.append({**t, **got, "year_accrued": year_acc, "kind": "спец"})
    partners: dict = {}
    for m in months:
        for r in rows_by[m]:
            for p in r["partners"]:
                k = (p["rule_id"], p["recipient_id"])
                e = partners.setdefault(k, {"kind": "партнёрская", "rule_id": p["rule_id"], "recipient_id": p["recipient_id"],
                                            "recipient": p.get("recipient"), "mode": p["mode"], "percent": p["percent"],
                                            "base": 0.0, "accrued": 0.0, "deals": 0, "status": "начислено"})
                e["base"] = _r2(e["base"] + float(r.get("base_net") or 0))
                e["accrued"] = _r2(e["accrued"] + float(p.get("amount") or 0))
                e["deals"] += 1
    year_partner = _r2(sum(float(p.get("amount") or 0) for m in upto for r in rows_by[m] for p in r["partners"]))
    part = sorted(partners.values(), key=lambda x: x["recipient"] or "")
    return {"period": period, "items": items, "partners": part,
            "kpi": {"accrued": _r2(sum(i["accrued"] for i in items) + sum(p["accrued"] for p in part)),
                    "accumulating": sum(1 for i in items if i["status"] == "копится"),
                    "year": _r2(sum(i["year_accrued"] for i in items) + year_partner)}}
