# -*- coding: utf-8 -*-
"""Блоки «Юрлицо и реквизиты» (cp) и «Подписанты» (sg) окна контрагента.

Проверки опираются на те же правила, по которым не собирается ДС: реквизиты — `annex_tpl/contract_check._side`,
подписант — `sales/annex.party`. Своих версий этих правил здесь нет.
"""
from datetime import date, timedelta
from typing import List

from sqlalchemy.orm import Session

from app.annex_tpl import contract_check
from app.models import Article, CounterpartyBankAccount
from app.readiness.checks import BAD, WARN, check
from app.sales.annex import party
from app.signers import service as SG

SOON_DAYS = 60          # «скоро» — то же окно, что лента «истекает в 60 дней»


def _article(db: Session, article_id):
    a = db.get(Article, article_id) if article_id else None
    return a.name if a else None


def cp_data(db: Session, cp) -> dict:
    banks = (db.query(CounterpartyBankAccount).filter(CounterpartyBankAccount.counterparty_id == cp.id)
             .order_by(CounterpartyBankAccount.sort_order, CounterpartyBankAccount.id).all())
    return {
        "id": cp.id, "name": cp.name, "legal_form": cp.legal_form,
        "inn": cp.inn, "kpp": cp.kpp, "ogrn": cp.ogrn, "okpo": cp.okpo,
        "address": cp.address, "fact_address": cp.address_fact, "phone": cp.phone, "email": cp.email,
        "site": cp.website, "edo_id": cp.edo_id, "signed_place": cp.signed_place,
        "term_days": cp.term_days,
        "sk_label": f"{cp.sk_mode} · {cp.sk_percent:g} %" if cp.sk_mode and cp.sk_percent is not None else (cp.sk_mode or None),
        "vat_in": cp.vat_rate_income, "vat_out": cp.vat_rate_expense,
        "item_in": _article(db, cp.default_article_income_id), "item_out": _article(db, cp.default_article_expense_id),
        "item_in_id": cp.default_article_income_id, "item_out_id": cp.default_article_expense_id,
        "status": cp.status, "ord_client_id": cp.ord_client_id, "is_own_company": bool(cp.is_own_company),
        "note": cp.note,                  # requisites перезаписывает его целиком — окно возвращает как есть
        # Основной счёт — первый по порядку: отдельного флага в базе нет (сверка спецификации, 04.11.2026).
        "banks": [{"id": b.id, "bank": b.bank_name, "bik": b.bik, "ks": b.ks, "rs": b.rs, "city": b.bank_city,
                   "main": i == 0} for i, b in enumerate(banks)],
    }


def cp_checks(db: Session, cp, on: date, kinds: List[str]) -> List[dict]:
    out = []
    fix = lambda field: {"block": "cp", "ref": cp.id, "field": field}  # noqa: E731
    for g in contract_check._side(cp, "юрлицо"):
        key = "kpp" if "КПП" in g["text"] else "inn"
        out.append(check(f"cp.{key}", "cp", BAD, g["text"].replace("юрлицо: ", "", 1).capitalize(),
                         "ДС не соберётся: это та же проверка, что при печати документа",
                         "annex_tpl/contract_check._side", fix(key)))
    if not (cp.inn or "").strip():
        out.append(check("cp.inn", "cp", BAD, "Нет ИНН", "ДС и ОРД без ИНН не соберутся", "sales/annex.party", fix("inn")))
    if len((cp.inn or "").strip()) == 12 and not cp.legal_form:
        out.append(check("cp.legal_form", "cp", BAD, "Не указана форма организации",
                         "ИНН из 12 цифр — ИП или физлицо: без формы ОРД клиента не зарегистрирует",
                         "ord/payloads.legal_form", fix("legal_form")))
    for key, label in (("ogrn", "ОГРН"), ("address", "юр. адрес")):
        if not (getattr(cp, key) or "").strip():
            out.append(check(f"cp.{key}", "cp", WARN, f"Нет: {label}", "нужен в шапке ДС и в ОРД",
                             "contract_card/readiness._requisites", fix(key)))
    if cp.term_days is None:
        out.append(check("cp.term_days", "cp", WARN, "Не задана отсрочка контрагента",
                         "дебиторка посчитает срок по умолчанию — 60 дней", "receivables._term_days_for_counterparty",
                         fix("term_days")))
    if "publisher" in kinds and cp.vat_rate_expense is None:
        out.append(check("cp.publisher_vat", "cp", BAD, "НДС площадки не указан",
                         "сверка месяца и разаллокация посчитают по ставке по умолчанию",
                         "publisher_recon.razaloc", fix("vat_out")))
    return out


def sg_data(db: Session, cp) -> List[dict]:
    from app.models import Contract
    from app.signers.models import ContractSigner
    where: dict = {}
    for cs, number in (db.query(ContractSigner, Contract.contract_number).join(Contract, Contract.id == ContractSigner.contract_id)
                       .filter(Contract.counterparty_id == cp.id).all()):
        where.setdefault(cs.signer_id, []).append(number or f"договор {cs.contract_id}")
    return [{"id": s.id, "name": s.director_name, "role": s.signer_position, "basis": s.signer_basis,
             "poa_until": s.valid_until, "is_default": bool(s.is_default), "archived": bool(s.is_archived),
             "where": where.get(s.id, [])} for s in SG.list_of(db, cp.id, archived=True)]


def sg_checks(db: Session, cp, on: date) -> List[dict]:
    out = []
    miss = [m for m in party(cp, SG.default_of(db, cp.id), on)["missing"] if m != "ИНН"]
    if miss:
        out.append(check("sg.default", "sg", BAD, "Нет подписанта по умолчанию: " + ", ".join(miss),
                         "без подписанта ДС не печатается", "sales/annex.party", {"block": "sg", "action": "add"}))
    for s in SG.list_of(db, cp.id):
        until = s.valid_until
        if not until:
            continue
        who = s.director_name or "подписант"
        if until < on:
            out.append(check(f"sg.poa.{s.id}", "sg", BAD, f"Доверенность истекла {until:%d.%m.%Y}: {who}",
                             "ДС с этим подписантом не соберётся", "sales/annex.party",
                             {"block": "sg", "ref": s.id, "action": "new_poa"}))
        elif until <= on + timedelta(days=SOON_DAYS):
            out.append(check(f"sg.poa.{s.id}", "sg", WARN, f"Доверенность истекает {until:%d.%m.%Y}: {who}",
                             f"через {(until - on).days} дн. ДС с этим подписантом не соберётся", "sales/annex.party",
                             {"block": "sg", "ref": s.id, "action": "new_poa"}))
    return out
