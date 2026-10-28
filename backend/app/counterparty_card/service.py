# -*- coding: utf-8 -*-
"""Сводка карточки контрагента v2 (хендофф «контрикZ», 28.10.2026): договоры с ДС, оборотом ДС за 12 месяцев, СК и состоянием;
плашка «Расчёты» (сальдо со знаком: нам должны − мы должны) со строкой причины по плановым операциям; тип контрагента; «в системе с»;
предупреждение, если операции идут без действующего договора; СК по контрагенту (правило основной СК на его агентство).
Карточка, аналитика и операции — прежними ручками; здесь только то, чего в них нет."""
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.contract_card.readiness import term_check
from app.counterparty_card.rules import kind_of, no_contract_warning, plan_reason
from app.permissions import get_permissions_for_user

_CONTRACTS = text("""
    SELECT k.id, k.contract_number, k.contract_date, k.cooperation_format, k.ord_kind, k.end_date_text, k.prolongation,
           (SELECT count(*) FROM sales_annexes a WHERE a.contract_id = k.id AND a.no IS NOT NULL) AS ds_count,
           coalesce((SELECT sum(a.total_amount) FROM sales_annexes a WHERE a.contract_id = k.id AND a.no IS NOT NULL
                      AND a.date >= :since), 0) AS ds_12m
      FROM contracts k WHERE k.counterparty_id = :cp ORDER BY k.contract_date DESC NULLS LAST, k.id DESC
""")

_OPS = text("""
    SELECT coalesce(sum(o.income), 0) AS income, coalesce(sum(o.expense), 0) AS expense, min(o.date) AS first, max(o.date) AS last,
           coalesce(sum(o.income) FILTER (WHERE o.status = 'ПЛАН ПОСТУПЛЕНИЙ'), 0) AS receivable,
           coalesce(sum(o.expense) FILTER (WHERE o.status = 'ПЛАН ОПЛАТ'), 0) AS payable, count(*) AS n
      FROM operations o WHERE o.counterparty_id = :cp
""")

_PLANS = text("""
    SELECT o.status, a.name AS article, o.period, o.invoice, o.invoice_date, o.bank
      FROM operations o LEFT JOIN articles a ON a.id = o.article_id
     WHERE o.counterparty_id = :cp AND o.status IN ('ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ')
     ORDER BY o.invoice_date DESC NULLS LAST, o.date DESC NULLS LAST, o.id DESC
""")


def _contracts(db: Session, cp_id: int, on: date, with_sk: bool) -> list:
    from app.contract_card.service import sk_of
    from app.models import Contract
    out = []
    for r in db.execute(_CONTRACTS, {"cp": cp_id, "since": on - timedelta(days=365)}).mappings().all():
        t = term_check(r["end_date_text"], r["prolongation"], on)
        row = {**dict(r), "ds_12m": float(r["ds_12m"]), "in_force": t["ok"], "term": t["text"]}
        if with_sk:
            s = sk_of(db, db.get(Contract, r["id"]), on)
            row["sk"] = f"{s['percent']:g} % · {s['mode']}" if s else None
        out.append(row)
    return out


def _sk(db: Session, cp_id: int, on: date):
    """СК по контрагенту: основная СК на его агентство (правило без договора, бренда и услуги)."""
    from app.agency_terms import rules as RL
    from app.agency_terms.service import all_rules
    rules = all_rules(db)
    for (ag, name) in db.execute(text("SELECT ac.agency_id, a.name FROM sales_agency_counterparties ac JOIN sales_agencies a "
                                      "ON a.id = ac.agency_id WHERE ac.counterparty_id = :cp"), {"cp": cp_id}).all():
        r = RL.pick(rules, {"agency_id": ag}, on, RL.MAIN)
        if r:
            return {"percent": r["percent"], "mode": r.get("mode"), "agency": name}
    return None


def overview(db: Session, cp, user) -> dict:
    perms = get_permissions_for_user(db, user)
    sk_right = bool((perms.get("sk_terms") or {}).get("view"))
    on = date.today()
    o = db.execute(_OPS, {"cp": cp.id}).mappings().first()
    contracts = _contracts(db, cp.id, on, sk_right)
    plans = [dict(p) for p in db.execute(_PLANS, {"cp": cp.id}).mappings().all()]
    receivable, payable = float(o["receivable"]), float(o["payable"])
    out = {
        "kind": kind_of(float(o["income"]), float(o["expense"])),
        "since": o["first"], "op_count": o["n"], "contracts": contracts,
        "settlement": {"receivable": receivable, "payable": payable, "saldo": receivable - payable, "reason": plan_reason(plans),
                       "plans": len(plans)},
        "warning": no_contract_warning(contracts, o["last"], on),
    }
    if sk_right:
        out["sk"] = _sk(db, cp.id, on)
    return out
