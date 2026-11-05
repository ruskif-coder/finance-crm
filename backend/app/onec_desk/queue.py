# -*- coding: utf-8 -*-
"""Очередь бухгалтерии и карточка комплекта: всё, что нужно, чтобы выставить УПД и счёт в 1С, не открывая пакет. Данные —
те же, что у мастер-сделки (основание — `to_annex.upds_of`, строки своей УПД — `annex_tpl.document._upd_own`), второй
сборки нет."""
import calendar
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.onec_desk.service import DONE, OPEN, RETURNED

TABS = ("wait", "returned", "done")

_ROWS = """
SELECT k.id AS kit_id, k.upd_no, k.brand, k.service, k.net, k.vat, k.gross, k.onec_state AS state,
       k.onec_invoice_no, k.onec_invoice_date, k.onec_upd_no, k.onec_upd_date, k.onec_gross, k.onec_at,
       m.id AS master_id, m.code AS master, m.period, m.status, m.updated_at AS since,
       c.contract_number, c.contract_date, cp.name AS buyer, cp.inn AS buyer_inn,
       a.number AS annex_number,
       (a.no IS NOT NULL OR a.origin = 'загружен') AS ds_ready,
       EXISTS (SELECT 1 FROM master_deal_files f WHERE f.master_deal_id = m.id AND f.upd_no = k.upd_no
                                                  AND f.kind = 'счёт 1С') AS invoice_pdf,
       EXISTS (SELECT 1 FROM master_deal_files f WHERE f.master_deal_id = m.id AND f.upd_no = k.upd_no
                                                  AND f.kind = 'УПД 1С') AS upd_pdf,
       (SELECT e.text FROM onec_desk_events e WHERE e.upd_id = k.id ORDER BY e.id DESC LIMIT 1) AS last_text
  FROM master_deal_upds k
  JOIN master_deals m ON m.id = k.master_deal_id
  JOIN contracts c ON c.id = m.contract_id
  LEFT JOIN counterparties cp ON cp.id = c.counterparty_id
  LEFT JOIN sales_annexes a ON a.id = k.annex_id
"""


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def queue(db: Session, tab: str = "wait", limit: int = 300) -> list:
    """wait — пакет ждёт 1С, комплект не внесён и не возвращён (старые сверху); returned — у аккаунта; done — внесённые (свежие сверху)."""
    if tab == "wait":
        # и пакеты, которые до 05.11.2026 двинули дальше «ждём 1С» руками, — их комплекты без ответа 1С тоже здесь (ревью)
        where, order = "m.status = ANY(:open) AND k.onec_state IS NULL", "m.updated_at, m.code, k.upd_no"
    elif tab == "returned":
        where, order = "k.onec_state = :r", "m.updated_at, m.code, k.upd_no"
    elif tab == "done":
        where, order = "k.onec_state = :d", "k.onec_at DESC NULLS LAST, m.code, k.upd_no"
    else:
        raise ValueError(tab)
    rows = db.execute(text(f"{_ROWS} WHERE {where} ORDER BY {order} LIMIT :n"),
                      {"open": list(OPEN), "r": RETURNED, "d": DONE, "n": limit}).mappings().all()
    return [{**{k: (float(v) if k in ("net", "vat", "gross", "onec_gross") and v is not None else v) for k, v in r.items()},
             **{k: _iso(r[k]) for k in ("onec_invoice_date", "onec_upd_date", "contract_date", "since", "onec_at")}}
            for r in rows]


def counts(db: Session) -> dict:
    r = db.execute(text("""SELECT count(*) FILTER (WHERE m.status = ANY(:open) AND k.onec_state IS NULL),
                                  count(*) FILTER (WHERE k.onec_state = :r),
                                  count(*) FILTER (WHERE k.onec_state = :d)
                             FROM master_deal_upds k JOIN master_deals m ON m.id = k.master_deal_id"""),
                   {"open": list(OPEN), "r": RETURNED, "d": DONE}).one()
    return {"wait": r[0], "returned": r[1], "done": r[2]}


def _party(cp) -> Optional[dict]:
    if cp is None:
        return None
    return {"id": cp.id, "name": cp.name, "inn": cp.inn, "kpp": cp.kpp, "ogrn": cp.ogrn, "address": cp.address}


def _last_day(period: str) -> str:
    y, mo = (int(x) for x in period.split("-"))
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"


def _lines(db: Session, k, annex, values: dict, rate: float) -> list:
    from app.annex_tpl import document as tpl_doc
    out = []
    for r in tpl_doc._upd_own(db, k, list(annex.rows or []), dict(values)) if annex is not None else []:
        net = round(float(r.get("amount") or 0), 2)
        vat = round(net * rate / 100, 2)
        out.append({"service": r.get("doc_position") or r.get("position") or "", "brand": r.get("brand") or "",
                    "kind": "доп" if r.get("kind") == "extra" else "размещение", "bonus": bool(r.get("bonus")),
                    "model": r.get("model") or "", "volume": r.get("volume"), "unit_price": r.get("unit_price"),
                    "date_from": r.get("date_from"), "date_to": r.get("date_to"),
                    "net": net, "vat_rate": rate, "vat": vat, "gross": round(net + vat, 2)})
    return out


def _ds_scan(db: Session, a) -> Optional[str]:
    """Имя скана подписанного бумажного ДС, если он есть."""
    if a is None:
        return None
    return db.execute(text("""SELECT filename FROM master_deal_files WHERE annex_id = :a AND kind = 'скан ДС'
                               ORDER BY id DESC LIMIT 1"""), {"a": a.id}).scalar()


def card(db: Session, k, upds: Optional[list] = None) -> dict:
    """upds — комплекты пакета с основаниями (`to_annex.upds_of`), если уже посчитаны: выгрузка пакета считает их один раз."""
    from app import own_company
    from app.master_deal import to_annex as TA
    from app.master_deal.models import MasterDeal
    from app.models import Contract, Counterparty
    from app.onec_desk import files as OF
    from app.onec_desk import service as SV
    from app.sales import annex_external as X
    from app.sales.models import SalesAnnex
    m = db.get(MasterDeal, k.master_deal_id)
    c = db.get(Contract, m.contract_id)
    a = db.get(SalesAnnex, k.annex_id) if k.annex_id else None
    buyer = db.get(Counterparty, c.counterparty_id) if c and c.counterparty_id else None
    payer = db.get(Counterparty, m.payer_counterparty_id) if m.payer_counterparty_id else None
    kit = next((x for x in (upds if upds is not None else TA.upds_of(db, m)) if x["upd_no"] == k.upd_no), {})
    net = float(k.net or 0)
    rate = float(a.vat_rate) if a is not None and a.vat_rate is not None else (round(float(k.vat or 0) / net * 100) if net else 0.0)
    lines = _lines(db, k, a, kit.get("values") or {}, rate)
    last_day = max((x["date_to"] for x in lines if x.get("date_to")), default=None)
    return {
        "kit_id": k.id, "upd_no": k.upd_no, "brand": k.brand, "service": k.service, "state": k.onec_state,
        "master": {"id": m.id, "code": m.code, "status": m.status, "period": m.period},
        "seller": _party(own_company.for_contract(db, c)) if c else None,
        "buyer": _party(buyer) or {"name": c.counterparty_name if c else None, "inn": c.inn if c else None, "kpp": None},
        "payer": _party(payer) if payer is not None and (buyer is None or payer.id != buyer.id) else None,
        "contract": {"id": c.id if c else None, "number": c.contract_number if c else None, "date": _iso(c.contract_date) if c else None},
        "annex": {"id": a.id if a else None, "number": (a.number if a else None) or kit.get("annex_number"),
                  "external": bool(a is not None and X.is_external(a)), "scan": _ds_scan(db, a),
                  "date": _iso(a.date) if a else None, "period_from": _iso(a.period_from) if a else None,
                  "period_to": _iso(a.period_to) if a else None},
        "lines": lines,
        "totals": {"net": net, "vat": float(k.vat or 0), "gross": float(k.gross or 0), "vat_rate": rate},
        "basis": kit.get("basis") or "",
        "upd_date_suggested": _last_day(m.period), "last_placement_day": last_day,
        "onec": {"invoice_no": k.onec_invoice_no, "invoice_date": _iso(k.onec_invoice_date), "upd_no": k.onec_upd_no,
                 "upd_date": _iso(k.onec_upd_date), "net": k.onec_net, "vat": k.onec_vat, "gross": k.onec_gross,
                 "at": k.onec_at.isoformat(timespec="seconds") if k.onec_at else None},
        "files": OF.files_of(db, m, k),
        "events": SV.events(db, k),
    }
