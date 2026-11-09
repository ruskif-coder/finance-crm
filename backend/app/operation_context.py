# -*- coding: utf-8 -*-
"""Связи операции для боковой панели реестра (владелец 09.11.2026: «операция теперь не оторванная от системы сущность»).

Форма ответа — контракт хендоффа `docs/design_handoff_operation_panel.zip` (`code/sampleData.js`): панель вставлена дословно и
считает строку «что дальше», статус и полосу оплаты сама (`operationLogic.js`), сервер их не присылает. Пустой блок — None / [].
Путь «операция → комплект → ДС → сделки» — `operations.master_deal_upd_id` (мост, `app/master_deal/bridge.py`).
Расхождения с контрактом: у ДС ещё `id` и полный `number` (короткое «ПР № 17» делает экран — правило одно, `lib/annexNumber.js`);
у документов — id файлов, а не адреса (файлы отдаются под авторизацией, ссылкой их не скачать); у оплаты — `op_id` строки цепочки
вместо `bank_row_id` (банковских строк в системе нет, оплата — это операция «ОПЛАЧЕНО» цепочки)."""
from datetime import timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import operation_chains as CH
from app.counterparty_card.rules import _ru     # «дд.мм.гггг» — своей копии не заводим
from app.models import PAID, PLAN_EXPENSE, PLAN_INCOME, Counterparty, Operation
from app.periods import month_label

ONEC_KINDS = {"счёт 1С": "inv_pdf_id", "УПД 1С": "upd_pdf_id", "УПД 1С xml": "upd_xml_id"}
BANK_KEY = {"АльфаБанк": "alfa", "ОПТ Банк": "opt", "Совкомбанк": "sovkom", "Наличные": "cash"}   # цвет маркера — `--bank-*`


def _d(v) -> Optional[str]:
    return v.isoformat() if v else None


def _utc(t) -> Optional[str]:
    """Время в базе — UTC без пояса; экран переводит в МСК."""
    return t.replace(tzinfo=timezone.utc).isoformat(timespec="seconds") if t else None


def _kit(db: Session, op):
    if not op.master_deal_upd_id:
        return None, None
    from app.master_deal.models import MasterDeal, MasterDealUpd
    k = db.get(MasterDealUpd, op.master_deal_upd_id)
    return (k, db.get(MasterDeal, k.master_deal_id)) if k else (None, None)


def _kind(op) -> tuple:
    if op.status == PLAN_INCOME:
        return "plan_income", "in"
    if op.status == PLAN_EXPENSE:
        return "plan_expense", "out"
    return ("expense", "out") if (op.expense or 0) > 0 and not (op.income or 0) else ("income", "in")


def _ds_and_deals(db: Session, k) -> tuple:
    if k is None or not k.annex_id:
        return None, []
    from app.sales.models import SalesAnnex
    a = db.get(SalesAnnex, k.annex_id)
    surface = (k.service or "").rpartition(" · ")[2] if " · " in (k.service or "") else ""   # «еФарм · WEB» — площадка комплекта
    deals = db.execute(text("""
        SELECT d.code, b.name AS brand, r.name AS account, ad.id AS advertiser_id,
               coalesce(nullif(trim(ad.legal_name), ''), ad.name, ad.short_name) AS advertiser,
               ag.id AS agency_id, coalesce(ag.name, ag.short_name) AS agency
          FROM sales_deal_annex_allocation x
          JOIN sales_deals d ON d.id = x.deal_id LEFT JOIN sales_brands b ON b.id = d.brand_id
          LEFT JOIN sales_reps r ON r.id = d.account_manager_id LEFT JOIN sales_advertisers ad ON ad.id = d.advertiser_id
          LEFT JOIN sales_agencies ag ON ag.id = d.agency_id
         WHERE x.annex_id = :a ORDER BY d.code"""), {"a": k.annex_id}).mappings().all()
    from app.sales import annex_external as X
    # внешний ДС (подписан вне системы) — смотреть нечего, только его файл или ссылка ЭДО; свой — печатная форма в системе
    ds = {"id": a.id, "number": a.number, "date": _d(a.date), "confirmed": a.no is not None, "amount": round(float(k.gross), 2),
          "external": X.is_external(a), "edo_link": a.edo_link,
          # файл внешнего ДС отдаёт `/annexes/{id}/external-file` — по последней загрузке к этому ДС
          "has_file": bool(db.execute(text("SELECT 1 FROM master_deal_files WHERE annex_id = :a LIMIT 1"), {"a": a.id}).first())} if a else None
    return ds, [{"code": x["code"], "brand": x["brand"], "surface": surface, "account": x["account"],
                 "advertiser": {"id": x["advertiser_id"], "name": x["advertiser"]} if x["advertiser_id"] else None,
                 # агентство, из-под которого шла сделка (владелец 09.11: «рядом с контриком… если есть»); имена агентства и
                 # рекламодателя — ПОЛНЫЕ (его же слово): у рекламодателя юрлицо, если вписано, иначе name; у агентства юрлица нет
                 "agency": {"id": x["agency_id"], "name": x["agency"]} if x["agency_id"] else None} for x in deals]


def _upd(db: Session, k, m, op) -> Optional[dict]:
    if k is None:
        return None
    files = {ONEC_KINDS[r.kind]: r.id for r in db.execute(text(
        "SELECT id, kind FROM master_deal_files WHERE master_deal_id = :m AND upd_no = :n AND kind = ANY(:k) ORDER BY id"),
        {"m": m.id, "n": k.upd_no, "k": list(ONEC_KINDS)})}
    by = db.execute(text("SELECT name FROM users WHERE id = :u"), {"u": k.onec_by}).scalar() if k.onec_by else None
    # комментарий бухгалтера к расхождению — обязателен при внесении с разницей (`onec_desk.service`), лежит в её ленте
    c = db.execute(text("""SELECT e.text, e.at, u.name FROM onec_desk_events e LEFT JOIN users u ON u.id = e.by_user
                            WHERE e.upd_id = :k AND e.kind IN ('внесено', 'правка') AND coalesce(e.text, '') <> ''
                            ORDER BY e.id DESC LIMIT 1"""), {"k": k.id}).first()
    return {"kit_id": k.id, "inv_no": k.onec_invoice_no, "inv_date": _d(k.onec_invoice_date), "upd_no": k.onec_upd_no,
            "upd_date": _d(k.onec_upd_date), "amount": round(float(k.onec_gross), 2) if k.onec_gross is not None else None,
            "basis": k.basis_text or op.description,          # своё основание комплекта, иначе — то, что мост вписал в операцию
            "entered_by": by, "entered_at": _utc(k.onec_at),
            "comment": c.text if c else None, "comment_by": c.name if c else None, "comment_at": _utc(c.at) if c else None,
            **{key: files.get(key) for key in ONEC_KINDS.values()}}


def _payments(db: Session, op) -> list:
    root = CH.root_id(op)
    chain = db.query(Operation).filter((Operation.id == root) | (Operation.parent_operation_id == root)).order_by(Operation.date, Operation.id).all()
    # at — день оплаты (календарный); created — момент записи строки, для ленты истории (день без времени там читался бы как «03:00»)
    return [{"op_id": x.id, "at": _d(x.date), "created": _utc(x.created_at), "amount": CH.amount(x), "bank": BANK_KEY.get(x.bank or ""),
             "doc": f"операция #{x.id}"} for x in chain if x.status == PAID]


def _due(db: Session, op, cp) -> tuple:
    if op.status != PLAN_INCOME or not op.income:
        return None, None
    from app.receivables import DEFAULT_TERM_DAYS, _due_date, _term_days_for_counterparty
    term = _term_days_for_counterparty(cp)
    rule = f"{term} дн. по условиям контрагента" if cp is not None and cp.term_days is not None else f"{DEFAULT_TERM_DAYS} дн. по умолчанию"
    return _d(_due_date(op.period, term)), rule


def _history(db: Session, op, k, payments) -> list:
    from app.audit_labels import ACTION_LABELS
    rows = db.execute(text("SELECT created_at, user_name, action FROM audit_log WHERE entity_type = 'operation' AND entity_id = :i"),
                      {"i": op.id}).all()
    out = [{"at": _utc(r.created_at), "text": ACTION_LABELS.get(r.action, r.action) + (f" — {r.user_name}" if r.user_name else ""),
            "kind": "create" if r.action.startswith("create") else "status"} for r in rows]
    if k is not None and k.onec_at:
        out.append({"at": _utc(k.onec_at), "text": "создана мостом — бухгалтер внёс комплект", "kind": "create"})
    out += [{"at": p["created"] or p["at"], "day": p["at"], "text": f"оплата {p['amount']:,.2f}".replace(",", " ") + f" от {_ru(p['at'])} · {p['doc']}",
             "kind": "money"} for p in payments if p["op_id"] != op.id]
    # новые сверху; оплаты, записанные одним заходом, — по дню оплаты
    out.sort(key=lambda h: (h["at"] or "", h.get("day") or ""), reverse=True)
    return [{key: h[key] for key in ("at", "text", "kind")} for h in out]


def _note(op, k) -> Optional[dict]:
    """Описание и вписанные руками реквизиты (владелец 09.11.2026: у старых и вне контура в описании «фиксировалась важная
    информация»). У операции моста их нет смысла дублировать: описание — это основание, № и счёт — в «Документах 1С»."""
    if k is not None:
        return None
    n = {"description": (op.description or "").strip() or None, "ds_num": op.ds_num or None, "invoice": op.invoice or None,
         "invoice_date": _d(op.invoice_date), "document_link": op.document_link or None}
    return n if any(n.values()) else None


def build(db: Session, op, can_download_docs: bool = False) -> dict:
    k, m = _kit(db, op)
    kind, direction = _kind(op)
    cp = db.get(Counterparty, op.counterparty_id) if op.counterparty_id else None
    own = db.get(Counterparty, op.own_company_id) if op.own_company_id else None
    ds, deals = _ds_and_deals(db, k)
    due_at, due_rule = _due(db, op, cp)
    payments = _payments(db, op)
    contract = None
    if m is not None and m.contract_id:
        r = db.execute(text("SELECT id, contract_number, contract_date FROM contracts WHERE id = :c"), {"c": m.contract_id}).first()
        contract = {"id": r.id, "no": r.contract_number, "date": _d(r.contract_date)} if r else None
    return {"id": op.id, "period": op.period, "period_label": month_label(op.period),
            "amount": round(float(op.income or op.expense or 0), 2), "vat": round(float(op.vat_fact or 0), 2), "vat_rate": op.vat_rate,
            "kind": kind, "direction": direction, "status_label": (op.status or "").lower(),
            "article": op.article.name if getattr(op, "article", None) else None, "due_at": due_at, "due_rule": due_rule,
            "package": {"code": m.code, "status_label": m.status, "upd_no": k.upd_no} if m is not None else None,
            "ds": ds, "deals": deals, "upd": _upd(db, k, m, op), "can_download_docs": bool(can_download_docs), "edo": None,
            "payments": payments, "counterparty": {"id": cp.id, "short": cp.name, "inn": cp.inn} if cp else None,
            "contract": contract, "our_entity": own.name if own else None, "note": _note(op, k),
            "history": _history(db, op, k, payments)}
