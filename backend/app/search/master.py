# -*- coding: utf-8 -*-
"""Поиск по контуру закрытия (владелец 21.10.2026): мастер-сделка по коду, УПД и счёт — по номеру из 1С.

Строка — тот же DTO, что у остальных типов (`types._row`), сумм нет. Ведёт в карточку пакета: УПД и счёт живут на его комплекте.
Видимость — функциями реестра мастер-сделок (`master_deal.scope`): «свои» видят пакет, если в нём есть их сделка. Пакетов —
сотни, поэтому отбор по области идёт после запроса, как у медиапланов; нет строки права — ничего (как `engine.deal_scope`)."""
from fastapi import HTTPException
from sqlalchemy import case, func, text

from app.master_deal import scope as SC
from app.master_deal.models import MasterDeal
from app.models import Contract
from app.periods import month_label
from app.search.types import _d, _esc, _row


def _own(db, ctx):
    if "master_own" not in ctx:
        try:
            ctx["master_own"] = ("ok", SC.own_reps(db, ctx["user"]))
        except HTTPException:
            ctx["master_own"] = ("none", None)
    return ctx["master_own"]


def _visible(db, ctx, masters) -> set:
    mode, own = _own(db, ctx)
    if mode == "none":
        return set()
    return {m.id for m in masters if SC.in_scope(db, m, own)}


def _code_form(q: str) -> str:
    """«м-1172», «M1172» → «M-1172»: код набирают русской «м» и без дефиса, в базе — латиницей с дефисом."""
    from app.search.classify import MASTER_CODE
    if not MASTER_CODE.match(q):
        return q
    return "M-" + q[1:].lstrip("-")


def master_deals(db, q, limit, offset, ctx):
    q = _code_form(q)
    pat = f"%{_esc(q)}%"
    ql = q.lower()
    rank = case((func.lower(MasterDeal.code) == ql, 0), (MasterDeal.code.ilike(f"{_esc(q)}%", escape="\\"), 1), else_=2)
    rows = (db.query(MasterDeal, Contract.contract_number, Contract.counterparty_name)
            .outerjoin(Contract, Contract.id == MasterDeal.contract_id)
            .filter(MasterDeal.code.ilike(pat, escape="\\") | Contract.contract_number.ilike(pat, escape="\\")
                    | Contract.counterparty_name.ilike(pat, escape="\\"))
            .order_by(rank, (MasterDeal.status == "архив"), MasterDeal.id.desc()).all())
    ok = _visible(db, ctx, [r[0] for r in rows])
    rows = [r for r in rows if r[0].id in ok][offset:offset + limit]
    return [_row(m.id, m.code, " · ".join(x for x in (m.status, f"№ {num}" if num else "", cp, month_label(m.period)) if x),
                 f"/accounts/master/{m.code}", m.status == "архив") for m, num, cp in rows]


def _kits(db, q, limit, offset, ctx, col: str, label: str, date_col: str = None):
    """УПД или счёт комплекта по номеру из 1С: точное совпадение раньше подстроки."""
    rows = db.execute(text(f"""
        SELECT k.id, k.{col} AS no, {('k.' + date_col) if date_col else 'NULL'} AS dt, k.upd_no, k.brand, k.master_deal_id
          FROM master_deal_upds k
         WHERE k.{col} ILIKE :p ESCAPE '\\'
         ORDER BY (lower(k.{col}) = :q) DESC, k.id DESC"""), {"p": f"%{_esc(q)}%", "q": q.lower()}).all()
    masters = {m.id: m for m in db.query(MasterDeal).filter(MasterDeal.id.in_({r.master_deal_id for r in rows} or {0}))}
    ok = _visible(db, ctx, masters.values())
    out = []
    for r in [r for r in rows if r.master_deal_id in ok][offset:offset + limit]:
        m = masters[r.master_deal_id]
        title = " от ".join(x for x in (f"{label} № {r.no}", _d(r.dt)) if x)
        sub = " · ".join(x for x in (m.code, f"комплект {r.upd_no}", r.brand) if x)
        out.append(_row(r.id, title, sub, f"/accounts/master/{m.code}", m.status == "архив"))
    return out


def upds(db, q, limit, offset, ctx):
    return _kits(db, q, limit, offset, ctx, "onec_upd_no", "УПД")


def invoices(db, q, limit, offset, ctx):
    return _kits(db, q, limit, offset, ctx, "onec_invoice_no", "Счёт", "onec_invoice_date")
