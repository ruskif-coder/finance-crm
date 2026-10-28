# -*- coding: utf-8 -*-
"""Доп. СК сделки — партнёрская выплата и доля спец. условий (владелец 27.10.2026): для «маржи с доп. СК» мастер-сделки.
Показывается рядом с обычной маржой и только тем, кому открыта вкладка «Спец. условия» (`sk_special`).

База — сумма ДС сделки до СК (как у основной и партнёрской СК, `calc._live_row`). Доля спец. условия:
- % без порога — % от суммы сделки;
- % с порогом — % от суммы сделки, если оборот года объекта вместе с ней дошёл до порога: после порога % идёт со всего года
  задним числом (`special.accrue`), то есть с каждой его сделки; не дошёл — 0 и «копится»;
- фикс — месячная доля (`special.term_months`), разложенная по сделкам объекта пропорционально их сумме в этом месяце.
Оборот объекта — закрытые сделки расчёта СК (`calc.month_rows`) без самой сделки: она прибавляется отдельно, закрыта она или нет.
Ядро (`deal_special`, `partner_amount`) — чистые функции."""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.agency_terms import special as SP


def _r2(v) -> float:
    return round(float(v or 0), 2)


def partner_amount(partners: List[dict], base: float) -> float:
    return _r2(sum(float(base or 0) * float(p["percent"] or 0) / 100.0 for p in partners))


def deal_special(term: dict, feat: dict, month: str, base: float, turn: Dict[str, float], month_all: Optional[float] = None) -> Optional[dict]:
    """Доля условия на сделку месяца `month` с суммой `base`; `turn` — оборот объекта по месяцам БЕЗ этой сделки."""
    if not SP.in_scope(term, feat) or not SP.covers(term, month):
        return None
    base = float(base or 0)
    if term.get("amount") is not None and term.get("percent") is None:
        months = SP.term_months(term)
        # знаменатель — все сделки объекта за месяц, и незакрытые тоже (ревью 27.10.2026): иначе каждая незакрытая брала весь месяц
        whole = float(month_all if month_all is not None else (turn.get(month) or 0)) + base
        share = float(term["amount"]) / len(months) * base / whole if (months and whole) else 0.0
        return {"amount": _r2(share), "status": "начислено"}
    pct = float(term.get("percent") or 0) / 100.0
    thr = term.get("threshold")
    if thr is not None:
        year = sum(float(v or 0) for k, v in turn.items() if k[:4] == month[:4] and SP.covers(term, k)) + base
        if year < float(thr):
            return {"amount": 0.0, "status": "копится"}
    return {"amount": _r2(base * pct), "status": "начислено"}


def of_deals(db: Session, items: List[tuple]) -> Dict[int, dict]:
    """[(сделка, сумма ДС до СК)] → {deal_id: {partner, special, extra, accumulating}}."""
    from app.agency_terms import calc as C
    from app.agency_terms import rules as R
    from app.agency_terms.models import SkSpecialTerm
    from app.agency_terms.service import special_dict
    from app.final_recon import sk as SK
    from app.timez import msk_now
    rules = SK._rules(db)
    terms = [special_dict(s) for s in db.query(SkSpecialTerm).order_by(SkSpecialTerm.id).all()]
    now = msk_now().strftime("%Y-%m")
    rows_by: Dict[str, dict] = {}

    def month_of(m):
        if m not in rows_by:
            rows_by[m] = C.month_rows(db, m) if m <= now else {"rows": [], "open": []}
        return rows_by[m]

    def rows_of(m):
        return month_of(m)["rows"]

    out = {}
    for deal, base in items:
        pf = getattr(deal, "period_from", None)
        if not pf or base is None:
            out[deal.id] = {"partner": 0.0, "special": 0.0, "extra": 0.0, "accumulating": []}
            continue
        month = pf.strftime("%Y-%m")
        feat = SK.features_of(deal)
        partner = partner_amount(R.pick_partners(rules, feat, R.close_date(month)), base)
        special, waiting = 0.0, []
        for t in terms:
            if not (SP.in_scope(t, feat) and SP.covers(t, month)):
                continue
            year = [f"{month[:4]}-{i:02d}" for i in range(1, 13)]
            turn = {m: sum(float(r.get("base_net") or 0) for r in rows_of(m) if r.get("deal_id") != deal.id and SP.in_scope(t, r))
                    for m in year}
            others = [x for x in month_of(month).get("open", []) if x.get("deal_id") != deal.id and SP.in_scope(t, x)]
            month_all = turn[month] + sum(float(x.get("estimate_net") or 0) for x in others)
            got = deal_special(t, feat, month, base, turn, month_all)
            special = _r2(special + got["amount"])
            if got["status"] == "копится":
                waiting.append(t.get("title") or f"условие {t['id']}")
        out[deal.id] = {"partner": partner, "special": special, "extra": _r2(partner + special), "accumulating": waiting}
    return out
