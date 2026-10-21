# -*- coding: utf-8 -*-
"""Документы пакета — одна модель для карточки и расхлопа реестра (хендофф «реестр + карточка», 19.10.2026).

ДС[] → комплекты УПД[]; у каждого документа — электронный файл, скан (бумага) и статус подписания:
  none   — не выпущен (ДС не подтверждён);
  issued — выпущен, не подписан;
  ours   — бумага: подписан нами, ждём клиента;
  sent   — ЭДО: отправлен; подпись клиента придёт из Диадока (до интеграции — так и остаётся);
  both   — бумага: скан подписанного приложен.
Счёт, УПД и Отчёт придут из 1С — до интеграции у комплекта их нет (`onec: False`), экран пишет «ждём 1С»."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import issue as IS
from app.master_deal import status as ST

EXTRA = "Доп. размещение"


def _signed(confirmed: bool, paper: bool, m, scan) -> str:
    if not confirmed:
        return "none"
    if paper:
        return "both" if scan else ("ours" if m.signed_by_us_at else "issued")
    return "sent" if m.sent_at else "issued"


def _services(rows: list) -> list:
    out = []
    for r in rows or []:
        s = EXTRA if r.get("kind") == "extra" else (r.get("position") or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _files(db: Session, m) -> dict:
    rows = db.execute(text("""SELECT id, annex_id, upd_no, filename, uploaded_at FROM master_deal_files
                               WHERE master_deal_id = :m"""), {"m": m.id}).all()
    out = {}
    for fid, a, u, name, at in rows:
        out[("a", a) if a is not None else ("u", u)] = {"id": fid, "filename": name, "at": at.isoformat(timespec="seconds") if at else None}
    return out


def build(db: Session, m) -> dict:
    from app.sales.models import SalesAnnex
    paper = ST.is_paper(db, m)
    files = _files(db, m)
    annexes = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id)
               .order_by(SalesAnnex.sub_no.isnot(None), SalesAnnex.sub_no, SalesAnnex.id).all())
    kits = db.execute(text("""SELECT upd_no, annex_id, brand, service, gross, onec_at, onec_invoice_no, onec_upd_no, net FROM master_deal_upds
                               WHERE master_deal_id = :m ORDER BY upd_no"""), {"m": m.id}).all()
    codes = {r[0]: r[1] for r in db.execute(text("""SELECT x.annex_id, string_agg(d.code, ', ' ORDER BY d.code)
                                                     FROM sales_deal_annex_allocation x JOIN sales_deals d ON d.id = x.deal_id
                                                    WHERE x.annex_id = ANY(:a) GROUP BY x.annex_id"""), {"a": [a.id for a in annexes] or [0]})}
    from app.master_deal import to_annex as TA
    numbers = {x["id"]: x["number"] for x in TA.annexes_of(db, m)}      # черновик тоже со своим номером: «ДС № 2-01»
    ds = []
    for a in annexes:
        confirmed = a.no is not None
        scan = files.get(("a", a.id))
        ds.append({
            "annex_id": a.id, "number": numbers.get(a.id) or a.number or f"ДС id {a.id}",
            "kind": "extra" if a.kind == "addons" else "base", "primary": a.issue_kind == "primary",
            "services": _services(a.rows), "gross": float(a.total_amount or 0), "confirmed": confirmed,
            "net": round(sum(float(r.get("amount") or 0) for r in (a.rows or [])), 2) if a.rows is not None else None,
            "doc_url": f"/annexes/{a.id}/docx", "scan": scan, "signed": _signed(confirmed, paper, m, scan),
            "kits": [{"upd_no": k[0], "group": " · ".join(x for x in (k[2], k[3]) if x) or "весь пакет", "gross": float(k[4] or 0),
                      "net": float(k[8] or 0), "deals": (codes.get(a.id) or "").split(", ") if codes.get(a.id) else [], "onec": bool(k[5]),
                      "invoice_no": k[6], "upd_doc_no": k[7],
                      "scan": files.get(("u", k[0])), "signed": _signed(confirmed, paper, m, files.get(("u", k[0])))}
                     for k in kits if k[1] == a.id],
        })
    req = IS.required_scans(db, m) if paper else []
    miss = IS.missing_scans(db, m) if paper else []
    return {"paper": paper, "ds": ds,
            "scans": {"need": paper and m.status in (ST.WAIT_PAY, ST.WAIT_SCANS, ST.ARCHIVE) and bool(m.sent_at),
                      "required": len(req), "have": len(req) - len(miss), "missing": miss,
                      "ds": [len([x for x in req if x["annex_id"]]), len([d for d in ds if d["scan"]])],
                      "upd": [len([x for x in req if x["upd_no"]]), sum(1 for d in ds for k in d["kits"] if k["scan"])],
                      "targets": [{"annex_id": x["annex_id"], "upd_no": x["upd_no"], "label": x["label"]} for x in req
                                  if x["label"] in miss]}}


def events(db: Session, m, limit: int = 10) -> list:
    rows = db.execute(text("""SELECT details, user_name, created_at FROM audit_log
                               WHERE entity_type = 'master_deal' AND entity_id = :m ORDER BY id DESC LIMIT :n"""),
                      {"m": m.id, "n": limit}).all()
    return [{"what": (d or "").split(": ", 1)[-1], "who": w or "система", "at": at.isoformat(timespec="seconds") if at else None}
            for d, w, at in rows]


def deal_price(db: Session, deal_id: int) -> Optional[dict]:
    """Цена за единицу и модель — из базовой строки МП сделки (первая не-доп строка)."""
    from app.sales import annex as annex_mod
    for r in annex_mod.plan_rows(db, [deal_id]):
        if r.get("kind") != "extra" and r.get("unit_price") is not None:
            return {"price": float(r["unit_price"]), "model": r.get("model") or ""}
    return None
