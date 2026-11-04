# -*- coding: utf-8 -*-
"""Блоки «Агентство» (ag), «Рекламодатели и бренды» (ad), «Условия СК» (sk), «ОРД» (ord) окна контрагента.

Агентство и рекламодатель — независимые сущности (владелец 04.11.2026): у агентства блока рекламодателей нет.
Рекламодатели здесь — те, плательщиком которых это юрлицо (`sales_advertiser_counterparties`).
СК — правило основной СК на договор, как в карточке договора (`contract_card.readiness.sk_summary`).
Изначальные договоры ОРД — где это юрлицо исполнитель (`ord_initial_contracts.contractor_inn`): связи рекламодателя с
агентством нет, поэтому «у рекламодателя нет изначального» не считается.
"""
import re
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agency_terms import rules as RL
from app.agency_terms.service import all_rules
from app.contract_card.readiness import sk_summary
from app.models import Contract
from app.ord.models import OrdInitialContract
from app.readiness import contracts as RC
from app.readiness.checks import BAD, WARN, check
from app.sales.models import (SalesAdvertiser, SalesAdvertiserCounterparty, SalesAgency, SalesAgencyCounterparty,
                              SalesBrand, SalesDeal)

KKTU = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")        # третий уровень, как требует ОРД (`payloads._kktu`)
SOON_DAYS = 60
REGISTERED = ("Active", "Registering", "RegistrationRequired")


def _agency_ids(db: Session, cp) -> List[int]:
    return [a for (a,) in db.query(SalesAgencyCounterparty.agency_id).filter(SalesAgencyCounterparty.counterparty_id == cp.id)]


def ag_data(db: Session, cp) -> Optional[dict]:
    ids = _agency_ids(db, cp)
    if not ids:
        return None
    a = db.get(SalesAgency, ids[0])
    legal = (db.query(SalesAgencyCounterparty.counterparty_id).filter(SalesAgencyCounterparty.agency_id == a.id).all())
    from app.models import Counterparty
    ents = db.query(Counterparty).filter(Counterparty.id.in_([x for (x,) in legal])).order_by(Counterparty.name).all()
    # Одно юрлицо бывает у нескольких агентств холдинга (АДЛАБС.РУ ООО — Adlabs и Havas, прод 04.11.2026): правится первое,
    # остальные называются — иначе их правила СК в окне выглядят чужими.
    others = db.query(SalesAgency).filter(SalesAgency.id.in_(ids)).order_by(SalesAgency.short_name).all()
    return {"id": a.id, "short_name": a.short_name, "holding": a.holding, "name_en": a.name_en, "name_ru": a.name_ru, "note": a.note,
            "legal_entities": [{"id": c.id, "name": c.name, "inn": c.inn, "self": c.id == cp.id} for c in ents],
            "agencies": [{"id": x.id, "short_name": x.short_name or x.name} for x in others]}


def ad_data(db: Session, cp) -> List[dict]:
    advs = (db.query(SalesAdvertiser).join(SalesAdvertiserCounterparty, SalesAdvertiserCounterparty.advertiser_id == SalesAdvertiser.id)
            .filter(SalesAdvertiserCounterparty.counterparty_id == cp.id).order_by(SalesAdvertiser.short_name, SalesAdvertiser.id).all())
    if not advs:
        return []
    brands: dict = {}
    for b in (db.query(SalesBrand).filter(SalesBrand.advertiser_id.in_([a.id for a in advs]))
              .order_by(SalesBrand.name).all()):
        brands.setdefault(b.advertiser_id, []).append({"id": b.id, "name": b.name, "kktu": b.kktu_code,
                                                       "ad_object": b.ad_object_description, "active": bool(b.is_active)})
    return [{"id": a.id, "legal_name": a.legal_name, "short_name": a.short_name, "inn": a.inn, "name_en": a.name_en,
             "name_ru": a.name_ru, "site": a.website, "sales_owner_id": a.sales_rep_id,
             "exclude_from_revenue": bool(a.exclude_from_revenue), "brands": brands.get(a.id, []),
             # ручка рекламодателя перезаписывает оба поля целиком — окно возвращает их как есть
             "note": a.note, "counterparty_id": a.counterparty_id} for a in advs]


def _advertiser_ids(db: Session, cp) -> List[int]:
    return [a for (a,) in db.query(SalesAdvertiserCounterparty.advertiser_id)
            .filter(SalesAdvertiserCounterparty.counterparty_id == cp.id)]


def _rules_of(rules: List[dict], ct_ids, ag_ids, adv_ids) -> List[dict]:
    return [r for r in rules if r.get("contract_id") in ct_ids or r.get("agency_id") in ag_ids
            or (r.get("advertiser_id") in adv_ids and r.get("agency_id") is None)]


def sk_data(db: Session, cp) -> List[dict]:
    """Правила СК юрлица с подписями: номер договора, агентство, рекламодатель — названием, а не номером строки
    (правило может быть на агентство, которое окно не правит: юрлицо у двух агентств)."""
    cts = [c for (c,) in db.query(Contract.id).filter(Contract.counterparty_id == cp.id)]
    rules = sorted(_rules_of(all_rules(db), set(cts), set(_agency_ids(db, cp)), set(_advertiser_ids(db, cp))),
                   key=lambda r: (r.get("valid_from") or date.min), reverse=True)
    ids = lambda k: {r[k] for r in rules if r.get(k)}  # noqa: E731
    numbers = dict(db.query(Contract.id, Contract.contract_number).filter(Contract.id.in_(ids("contract_id") or {0})).all())
    agencies = {a.id: a.short_name or a.name for a in db.query(SalesAgency).filter(SalesAgency.id.in_(ids("agency_id") or {0}))}
    advs = {a.id: a.short_name or a.name for a in db.query(SalesAdvertiser).filter(SalesAdvertiser.id.in_(ids("advertiser_id") or {0}))}
    return [{**r, "contract_number": numbers.get(r.get("contract_id")), "agency_name": agencies.get(r.get("agency_id")),
             "advertiser_name": advs.get(r.get("advertiser_id"))} for r in rules]


def ord_data(db: Session, cp) -> dict:
    cts = db.query(Contract).filter(Contract.counterparty_id == cp.id).order_by(Contract.id).all()
    deals = dict(db.query(SalesDeal.ord_final_contract_id, func.count(SalesDeal.id))
                 .filter(SalesDeal.ord_final_contract_id.in_([c.id for c in cts] or [0]))
                 .group_by(SalesDeal.ord_final_contract_id).all())
    initial = (db.query(OrdInitialContract).filter(OrdInitialContract.contractor_inn == cp.inn).order_by(OrdInitialContract.id).all()
               if (cp.inn or "").strip() else [])
    return {"contracts": [{"contract_id": c.id, "contract": c.contract_number, "kind": c.ord_kind, "ord_id": c.ord_contract_id,
                           "status": c.ord_status, "env": c.ord_env, "deals": deals.get(c.id, 0)} for c in cts],
            "initial": [{"id": i.id, "advertiser": i.advertiser_name, "advertiser_inn": i.advertiser_inn, "number": i.number,
                         "date": i.date, "subject": i.subject_type, "amount": i.amount,
                         "agent_for_publisher": i.is_agent_acting_for_publisher, "status": i.status,
                         "error": i.error_text} for i in initial]}


def checks(db: Session, cp, on: date) -> List[dict]:
    out = []
    cts = db.query(Contract).filter(Contract.counterparty_id == cp.id).order_by(Contract.id).all()
    tags = set().union(*[RC.template_tags(db, c) for c in cts]) if cts else set()
    for a in ad_data(db, cp):
        name = a["short_name"] or "рекламодатель"
        if not (a["legal_name"] or "").strip():
            bad = "юр_название" in tags
            out.append(check(f"ad.legal_name.{a['id']}", "ad", BAD if bad else WARN, f"{name}: нет юр. названия",
                             "подстановка {юр_название} в ДС будет пустой" if bad else "шаблоны договоров его пока не используют",
                             "annex_tpl/assemble._legal_names", {"block": "ad", "ref": a["id"], "field": "legal_name"}))
        for b in a["brands"]:
            if b["active"] and not KKTU.match((b["kktu"] or "").strip()):
                out.append(check(f"ad.kktu.{b['id']}", "ad", BAD, f"{b['name']}: нет ККТУ третьего уровня",
                                 "ЕРИД по бренду не выпустится", "ord/payloads._kktu",
                                 {"block": "ad", "ref": b["id"], "field": "kktu"}))
    od = ord_data(db, cp)
    for c in od["contracts"]:
        if c["ord_id"] and c["kind"] == "final":
            continue
        out.append(check(f"ord.contract.{c['contract_id']}", "ord", BAD if c["deals"] else WARN,
                         f"{c['contract'] or c['contract_id']} не зарегистрирован в ОРД",
                         f"по договору уже {c['deals']} сделок — ЕРИД по ним не выпустится" if c["deals"]
                         else "пока по нему нет сделок; станет красным с первой сделкой", "ord/matching.resolve_final",
                         {"link": "/accounts/ord"}))
    for i in od["initial"]:
        if i["status"] not in REGISTERED:
            out.append(check(f"ord.initial.{i['id']}", "ord", BAD, f"Изначальный договор {i['number'] or i['id']} "
                             f"({i['advertiser'] or i['advertiser_inn']}) не зарегистрирован",
                             i["error"] or f"статус в ОРД: {i['status'] or 'не получен'}", "ord/submit.register_initial_contract",
                             {"link": "/accounts/ord"}))
    rules = all_rules(db)
    ag, adv = _agency_ids(db, cp), _advertiser_ids(db, cp)
    for c in cts:
        if sk_summary(rules, c.id, ag, adv, on) is None:
            out.append(check(f"sk.missing.{c.id}", "sk", WARN, f"{c.contract_number or c.id}: нет правила СК",
                             "сделки по договору пойдут без агентской комиссии в расчёте", "contract_card/readiness.sk_summary",
                             {"block": "sk", "action": "add"}))
    for r in _rules_of(rules, {c.id for c in cts}, set(ag), set(adv)):
        till = r.get("valid_to")
        if r["kind"] == RL.MAIN and RL.active(r, on) and till and till <= on + timedelta(days=SOON_DAYS):
            out.append(check(f"sk.expiring.{r['id']}", "sk", WARN, f"Правило СК {r['percent']:g} % истекает {till:%d.%m.%Y}",
                             "после срока сделки пойдут без СК", "agency_terms/rules.active", {"block": "sk", "ref": r["id"]}))
    return out
