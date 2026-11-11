# -*- coding: utf-8 -*-
"""Правки отчёта ОРД из Excel (`ord_report_overrides`) и отчёт месяца с правками. Только flush — коммит и журнал в роутере."""
from datetime import date
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ord import month_report as MR
from app.ord.report_models import OrdReportOverride

FIELDS = ("deal_code", "deal_id", "publisher_id", "domain", "erid", "kind") + MR.EDITABLE


def parse_month(s: str) -> date:
    try:
        y, m = (int(x) for x in s.split("-"))
        return date(y, m, 1)
    except (ValueError, AttributeError):
        raise MR.ReportError("Месяц — в виде ГГГГ-ММ")


def overrides(db: Session, month: date) -> List[dict]:
    out = []
    for o in db.query(OrdReportOverride).filter(OrdReportOverride.month == month).order_by(OrdReportOverride.id):
        d = {f: getattr(o, f) for f in FIELDS}
        out.append({**d, "amount": float(d["amount"]) if d["amount"] is not None else None,
                    "upd_gross": float(d["upd_gross"]) if d["upd_gross"] is not None else None})
    return out


def meta(db: Session, month: date) -> Optional[dict]:
    r = db.execute(text("""SELECT o.imported_at, o.filename, u.name, count(*) OVER () AS n
                             FROM ord_report_overrides o LEFT JOIN users u ON u.id = o.imported_by
                            WHERE o.month = :m ORDER BY o.id DESC LIMIT 1"""), {"m": month}).mappings().first()
    return None if r is None else {"at": r["imported_at"].isoformat(), "filename": r["filename"], "by": r["name"], "count": r["n"]}


def report(db: Session, month: date) -> List[dict]:
    """Расчёт месяца с правками из файла."""
    return MR.apply_overrides(MR.compute(db, month), overrides(db, month))


def _resolve(db: Session, ovs: List[dict]) -> List[dict]:
    """Добавленным строкам — сделка по коду и площадка по домену, если найдутся (иначе ссылка пустая)."""
    codes = {o["deal_code"] for o in ovs if o.get("deal_id") is None}
    doms = {o["domain"] for o in ovs if o.get("publisher_id") is None and o.get("domain")}
    deal = dict(db.execute(text("SELECT upper(code), id FROM sales_deals WHERE upper(code) = ANY(:c)"), {"c": list(codes) or [""]}).all())
    pub = dict(db.execute(text("SELECT lower(domain), id FROM sales_publishers WHERE lower(domain) = ANY(:d)"), {"d": list(doms) or [""]}).all())
    return [{**o, "deal_id": o.get("deal_id") or deal.get(o["deal_code"]),
             "publisher_id": o.get("publisher_id") or pub.get(o["domain"])} for o in ovs]


def import_file(db: Session, month: date, file_rows: List[dict], user_id: Optional[int], filename: Optional[str]) -> dict:
    """Файл → отличия от расчёта; прежние правки месяца заменяются. Файл не про этот месяц — отказ."""
    if not file_rows:
        # шапка без строк превратила бы весь расчёт в «убрана» — месяц опустел бы одной загрузкой (ревью 11.11.2026)
        raise MR.ReportError("В файле нет строк отчёта — загружать нечего")
    calc = MR.compute(db, month)
    codes = {MR.key(r)[0] for r in calc}
    mine = sum(1 for r in file_rows if r["deal_code"] in codes)
    if file_rows and calc and mine * 2 < len(file_rows):
        raise MR.ReportError(f"Сделок этого месяца в файле {mine} из {len(file_rows)} — похоже, файл за другой месяц")
    ovs = _resolve(db, MR.diff(calc, file_rows))
    db.query(OrdReportOverride).filter(OrdReportOverride.month == month).delete(synchronize_session=False)
    for o in ovs:
        db.add(OrdReportOverride(month=month, imported_by=user_id, filename=(filename or "")[:255],
                                 **{f: o.get(f) for f in FIELDS}))
    db.flush()
    return {k: sum(1 for o in ovs if o["kind"] == k) for k in ("правка", "добавлена", "убрана")}


def reset(db: Session, month: date) -> int:
    n = db.query(OrdReportOverride).filter(OrdReportOverride.month == month).delete(synchronize_session=False)
    db.flush()
    return n


def months(db: Session) -> List[dict]:
    """Месяцы, где есть мастер-сделки, — свежие сверху, с числом УПД, внесённых из 1С, правок и строк снимка ЕРИД."""
    rows = db.execute(text("""
        SELECT m.period, count(DISTINCT k.id) AS kits, count(DISTINCT k.id) FILTER (WHERE k.onec_upd_no IS NOT NULL) AS with_upd
          FROM master_deals m JOIN master_deal_upds k ON k.master_deal_id = m.id
         GROUP BY 1 ORDER BY 1 DESC""")).mappings().all()
    ov = dict(db.execute(text("SELECT to_char(month, 'YYYY-MM'), count(*) FROM ord_report_overrides GROUP BY 1")).all())
    sn = dict(db.execute(text("SELECT to_char(month, 'YYYY-MM'), max(captured_at) FROM ord_erid_month_stat GROUP BY 1")).all())
    return [{"month": r["period"], "kits": r["kits"], "with_upd": r["with_upd"], "overrides": ov.get(r["period"], 0),
             "snapshot_at": sn[r["period"]].isoformat() if sn.get(r["period"]) else None} for r in rows]
