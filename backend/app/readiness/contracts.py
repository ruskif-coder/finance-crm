# -*- coding: utf-8 -*-
"""Блоки «Договоры» (ct) и «Шаблоны документов» (tpl) окна контрагента.

Проверки — те же правила, по которым ДС не собирается: реквизиты договора — `annex_tpl/contract_check.gaps`, подписанты
сторон — `signers.service.for_side`, шаблон — `annex_tpl/service.resolve_for_contract`, срок — `contract_card/readiness.term_check`.
Договоры контрагента — где он `counterparty_id`; договоры, где он наше юрлицо (`own_company_id`), сюда не входят.
"""
import re
from datetime import date
from typing import List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import own_company
from app.annex_tpl import contract_check
from app.annex_tpl import service as TS
from app.contract_card.readiness import term_check
from app.models import Contract
from app.readiness.checks import BAD, WARN, check
from app.signers import service as SG

_KEY = re.compile(r"\{([^{}]+)\}")          # тот же образец тега, что в annex_tpl/assemble._KEY
ROLES = {"EXECUTOR": "исполнитель", "AGENT": "агент", "CUSTOMER": "заказчик"}
_WORDS = {"дс": "ДС", "приложение": "Приложение"}      # коды `annex_tpl/doc_kind.KINDS`


def _contracts(db: Session, cp) -> List[Contract]:
    return db.query(Contract).filter(Contract.counterparty_id == cp.id).order_by(Contract.contract_date.desc().nullslast(),
                                                                                 Contract.id.desc()).all()


def _signer_label(s) -> Optional[str]:
    if s is None or not s.director_name:
        return None
    return f"{s.director_name} — {s.signer_position}" if s.signer_position else s.director_name


def _cpm(db: Session, ct) -> tuple:
    """(есть ли у договора площадка, её CPM): CPM хранится у площадки (`sales_publishers.cpm_contract`)."""
    from app.sales.models import SalesPublisher, SalesPublisherContract
    row = (db.query(SalesPublisher.cpm_contract).join(SalesPublisherContract, SalesPublisherContract.publisher_id == SalesPublisher.id)
           .filter(SalesPublisherContract.contract_id == ct.id, SalesPublisherContract.is_archived.isnot(True)).first())
    return (row is not None, row[0] if row else None)


def _extra(db: Session, ids: List[int]) -> dict:
    """Колонки договора без ORM-атрибутов (`nds`, `own_legal_role`, `edo_*`) — тем же сырым SQL, что карточка договора
    (`contract_card/service.head`), одним запросом на всех."""
    if not ids:
        return {}
    rows = db.execute(text("SELECT id, nds, own_legal_role, edo_status, edo_signed_at FROM contracts WHERE id = ANY(:i)"),
                      {"i": ids}).mappings().all()
    return {r["id"]: r for r in rows}


def ct_data(db: Session, cp) -> List[dict]:
    out = []
    cts = _contracts(db, cp)
    ex = _extra(db, [c.id for c in cts])
    for ct in cts:
        e = ex.get(ct.id, {})
        us = own_company.for_contract(db, ct)
        cust, _ = SG.for_side(db, ct, "заказчик")
        ours, _ = SG.for_side(db, ct, "исполнитель")
        is_pub, cpm = _cpm(db, ct)
        out.append({
            "id": ct.id, "number": ct.contract_number, "date": ct.contract_date, "marketing_name": ct.marketing_name,
            "own_company": us.name if us else None, "own_legal_role": ROLES.get(e.get("own_legal_role") or "", e.get("own_legal_role")),
            "format": ct.cooperation_format, "services": ct.services,
            "customer_signer": _signer_label(cust), "our_signer": _signer_label(ours),
            "customer_signer_id": getattr(cust, "id", None), "our_signer_id": getattr(ours, "id", None),
            "vat": None if e.get("nds") is None else ("с НДС" if e.get("nds") else "без НДС"),
            "pay_form": ct.payment_form, "payment_term_days": ct.payment_term_days, "term_cond": ct.payment_term_condition,
            "valid_until": ct.end_date_text, "prolongation": ct.prolongation, "channel": ct.issue_channel,
            "edo_status": " · ".join(x for x in (e.get("edo_status"), f"{e['edo_signed_at']:%d.%m.%Y}" if e.get("edo_signed_at") else None)
                                     if x) or None,
            "annex_word": _WORDS.get(ct.annex_word or "", ct.annex_word), "annex_start_no": ct.annex_start_no, "note": ct.note,
            "document_url": ct.document_link,
            "document_file": {"name": ct.attached_filename} if ct.attached_filename else None,
            "is_publisher_contract": is_pub, "cpm": cpm,
        })
    return out


def _fix(ct, field):
    return {"block": "ct", "ref": ct.id, "field": field}


def ct_checks(db: Session, cp, on: date) -> List[dict]:
    out = []
    for ct in _contracts(db, cp):
        n = ct.contract_number or f"договор {ct.id}"
        for g in contract_check.gaps(db, ct):
            t = g["text"]
            if t.startswith(("заказчик:", "исполнитель:")):
                continue                      # реквизиты сторон горят в блоке «Юрлицо» (и у нашего юрлица — в его окне)
            key = ("number" if "номер" in t else "date" if "дата" in t else "channel" if "выставление" in t
                   else "own_company" if "юрлицо" in t else "counterparty")
            out.append(check(f"ct.{key}.{ct.id}", "ct", BAD, f"{n}: {t.replace('договор: ', '')}", "ДС по договору не соберётся",
                             "annex_tpl/contract_check.gaps", _fix(ct, key)))
        if not (ct.cooperation_format or "").strip():
            out.append(check(f"ct.format.{ct.id}", "ct", BAD, f"{n}: нет формата сотрудничества",
                             "без него договору не подобрать шаблон ДС — ДС не соберётся",
                             "annex_tpl/service.resolve_for_contract", _fix(ct, "format")))
        for side, key, title, why in (("заказчик", "customer_signer", "нет подписанта заказчика", "в ДС не будет подписи заказчика"),
                                      ("исполнитель", "our_signer", "не выбран наш подписант", "в ДС не будет подписи исполнителя")):
            if SG.for_side(db, ct, side)[0] is None:
                out.append(check(f"ct.{key}.{ct.id}", "ct", BAD, f"{n}: {title}", why, "signers/service.for_side", _fix(ct, key)))
        if ct.payment_term_days is not None and cp.term_days is not None and ct.payment_term_days != cp.term_days:
            out.append(check(f"ct.term.{ct.id}", "ct", WARN, f"{n}: отсрочка {ct.payment_term_days}, у контрагента {cp.term_days}",
                             "дебиторка считает по отсрочке контрагента — сроки в отчёте разойдутся с договором",
                             "receivables._term_days_for_counterparty", _fix(ct, "payment_term_days")))
        if not (ct.document_link or ct.attached_filename):
            out.append(check(f"ct.document.{ct.id}", "ct", WARN, f"{n}: нет файла или ссылки на договор",
                             "юристу не на что опереться при споре", "contract_card", _fix(ct, "document_url")))
        t = term_check(ct.end_date_text, ct.prolongation, on)
        if not t["ok"]:
            out.append(check(f"ct.valid_until.{ct.id}", "ct", BAD if "истёк" in t["text"] else WARN, f"{n}: {t['text']}",
                             "по договору без срока размещения идут без основания", "contract_card/readiness.term_check",
                             _fix(ct, "valid_until")))
        is_pub, cpm = _cpm(db, ct)
        if is_pub and not cpm:
            out.append(check(f"ct.cpm.{ct.id}", "ct", BAD, f"{n}: нет CPM по договору площадки",
                             "сверке месяца не из чего посчитать сумму площадке", "publisher_recon", _fix(ct, "cpm")))
    return out


def template_tags(db: Session, contract) -> Set[str]:
    """Теги шаблона, которым соберётся ДС по договору (`resolve_for_contract`); шаблона нет — пусто."""
    t = TS.resolve_for_contract(db, contract).get("template")
    v = TS.current(db, t.id) if t is not None else None
    if v is None:
        return set()
    return {k.strip() for b in (v.blocks or []) for k in _KEY.findall(b.get("text") or "")}


_WHY = {"chosen": "выбран вручную", "brand": "запомнен по бренду", "main": "основной договора", "format": "базовый формата"}


def tpl_data(db: Session, cp) -> dict:
    rows = []
    for ct in _contracts(db, cp):
        r = TS.resolve_for_contract(db, ct)
        t = r.get("template")
        v = TS.current(db, t.id) if t is not None else None
        rows.append({"contract_id": ct.id, "contract": ct.contract_number, "template": t.title if t else None,
                     "origin": _WHY.get(r.get("why")), "version": f"v{v.version}" if v else None,
                     "reason": r.get("reason"), "check": "ok" if t else "bad"})
    return {"templates": rows}


def tpl_checks(db: Session, cp) -> List[dict]:
    out = []
    for ct in _contracts(db, cp):
        r = TS.resolve_for_contract(db, ct)
        if r.get("template") is None:
            out.append(check(f"tpl.resolve.{ct.id}", "tpl", BAD, f"{ct.contract_number or ct.id}: шаблон ДС не подберётся",
                             r.get("reason") or "шаблона нет", "annex_tpl/service.resolve_for_contract",
                             {"block": "ct", "ref": ct.id, "field": "format"}))
    return out
