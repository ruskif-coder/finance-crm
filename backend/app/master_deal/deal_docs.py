# -*- coding: utf-8 -*-
"""Документы сделки — из мастер-сделки (владелец 13.11.2026: «документы показываем из мастер-сделки, ручную загрузку ДС,
счёта, УПД и акта убираем»).

Документы живут в одном месте — в пакете; карточка сделки и доски их ПОКАЗЫВАЮТ, не копируя. Правило одно на три случая:
сделка видит документы, в которых есть её строки, и свою долю в каждом.
  · ДС — по разнесению сумм (`sales_deal_annex_allocation`): все ДС, где у сделки есть доля (стартовый ДС — тоже);
  · комплект (счёт + УПД) — по разбивке `master_deal_upds.deals`, которую пишет раскладка при создании ДС.
Пакет из одной сделки — всё «один к одному», без долей; из нескольких — у комплекта «общий с …»."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def _master_of(db: Session, deal_id: int) -> Optional[dict]:
    r = db.execute(text("""SELECT m.id, m.code, m.status FROM master_deal_items i JOIN master_deals m ON m.id = i.master_deal_id
                            WHERE i.deal_id = :d ORDER BY m.id DESC LIMIT 1"""), {"d": deal_id}).first()
    return {"id": r[0], "code": r[1], "status": r[2]} if r else None


def _ds(db: Session, deal_id: int) -> list:
    rows = db.execute(text("""
        SELECT a.id, a.no, a.number, a.date, a.sign_state, a.master_deal_id, al.amount, a.total_amount,
               (SELECT array_agg(d2.code ORDER BY d2.code) FROM sales_deal_annex_allocation o JOIN sales_deals d2 ON d2.id = o.deal_id
                 WHERE o.annex_id = a.id AND o.deal_id <> :d) AS others
          FROM sales_deal_annex_allocation al JOIN sales_annexes a ON a.id = al.annex_id
         WHERE al.deal_id = :d
         ORDER BY a.no IS NULL, a.no, a.sub_no NULLS FIRST, a.id"""), {"d": deal_id}).mappings().all()
    return [{"id": r["id"], "no": r["no"], "number": r["number"], "date": r["date"], "is_draft": r["no"] is None,
             "sign_state": r["sign_state"], "master_deal_id": r["master_deal_id"],
             "share": round(float(r["amount"] or 0), 2), "total": round(float(r["total_amount"] or 0), 2),
             "shared_with": list(r["others"] or [])} for r in rows]


def _kits(db: Session, deal_id: int) -> list:
    from app.onec_desk import files as OF
    from app.master_deal.models import MasterDeal, MasterDealUpd
    rows = (db.query(MasterDealUpd, MasterDeal.code)
            .join(MasterDeal, MasterDeal.id == MasterDealUpd.master_deal_id)
            .filter(MasterDealUpd.deals.contains([{"deal_id": deal_id}]))
            .order_by(MasterDeal.id, MasterDealUpd.upd_no).all())
    out = []
    for k, code in rows:
        share = next((x for x in k.deals if x.get("deal_id") == deal_id), {})
        m = db.get(MasterDeal, k.master_deal_id)
        files = OF.files_of(db, m, k)
        out.append({
            "master_code": code, "upd_no": k.upd_no, "annex_id": k.annex_id, "brand": k.brand, "service": k.service,
            "invoice_no": k.onec_invoice_no, "invoice_date": k.onec_invoice_date,
            "upd_no_1c": k.onec_upd_no, "upd_date": k.onec_upd_date,
            "in_1c": k.onec_state == "внесён", "sign_state": k.sign_state,
            "share_net": round(float(share.get("net") or 0), 2), "share_gross": round(float(share.get("gross") or 0), 2),
            "total_gross": round(float(k.onec_gross if k.onec_gross is not None else k.gross or 0), 2),
            "shared_with": sorted(x.get("code") for x in k.deals if x.get("deal_id") != deal_id),
            "files": {slot: f["id"] for slot, f in files.items() if slot in ("invoice", "upd")},
        })
    return out


def for_deal(db: Session, deal) -> dict:
    """{master: {id, code, status} | None, ds: [...], kits: [...]} — документы сделки из её мастер-сделки."""
    return {"master": _master_of(db, deal.id), "ds": _ds(db, deal.id), "kits": _kits(db, deal.id)}


def state(docs: dict, kind: str) -> int:
    """Индикатор вида документа для досок: 0 — все готовы, 1 — часть / в работе, 2 — нет. ДС готов, когда выпущен (с
    номером); счёт и УПД — когда бухгалтер внесла их из 1С."""
    items = docs.get("ds") if kind == "ds" else docs.get("kits")
    if not items:
        return 2
    ready = [x for x in items if (not x["is_draft"] if kind == "ds" else x["in_1c"])]
    return 0 if len(ready) == len(items) else 1
