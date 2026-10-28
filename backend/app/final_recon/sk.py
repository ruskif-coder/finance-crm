# -*- coding: utf-8 -*-
"""СК сделки на закрытии. С 27.10.2026 источник — «Агентские условия» (`app/agency_terms`): правило по договору закрытия и
агентству (рекламодателю), уточнения брендом и услугой; на сделке — своя поправка, аккаунт правит. СК юрлица
(`counterparties.sk_*`, 14.10.2026) — история. Без способа СК не закрыть Альфарм-Таргет."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.final_recon.models import SK_MODES, FinalReconDeal
from app.models import Counterparty


class SkError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def validate(mode: Optional[str], percent: Optional[float]) -> None:
    if mode is not None and mode not in SK_MODES:
        raise SkError(400, f"Способ СК — {' или '.join(SK_MODES)}")
    if percent is not None and not (0 <= percent <= 100):
        raise SkError(400, "Процент СК — от 0 до 100")


def payer_of(db: Session, deal) -> Optional[Counterparty]:
    """Юрлицо закрытия, чей СК действует: плательщик сделки, а если он не задан — контрагент доходного договора (владелец 19.10.2026:
    закрываем на контрагента доходного договора; у двух сделок стенда плательщик пуст при выбранном договоре — СК терялся)."""
    pid = getattr(deal, "payer_counterparty_id", None)
    if not pid and getattr(deal, "ord_final_contract_id", None):
        from app.models import Contract
        c = db.get(Contract, deal.ord_final_contract_id)
        pid = c.counterparty_id if c else None
    return db.query(Counterparty).filter(Counterparty.id == pid).first() if pid else None


def _rules(db: Session) -> list:
    """Правила «Агентских условий» — один раз на запрос (реестр мастер-сделок считает сверку десяткам сделок)."""
    cache = getattr(db, "info", None)
    if cache is not None and "sk_rules" in cache:
        return cache["sk_rules"]
    from app.agency_terms.service import all_rules
    got = all_rules(db)
    if cache is not None:
        cache["sk_rules"] = got
    return got


def features_of(deal) -> dict:
    """Признаки сделки для подбора правила: договор закрытия, агентство, рекламодатель, бренд, услуга."""
    return {"contract_id": getattr(deal, "ord_final_contract_id", None), "agency_id": getattr(deal, "agency_id", None),
            "advertiser_id": getattr(deal, "advertiser_id", None), "brand_id": getattr(deal, "brand_id", None),
            "service_id": getattr(deal, "service_id", None)}


def rule_of(db: Session, deal) -> Optional[dict]:
    """Основная СК сделки по «Агентским условиям» — самое точное правило на момент закрытия её месяца (последний день)."""
    from app.agency_terms import rules as R
    pf = getattr(deal, "period_from", None)
    if not pf:
        return None
    return R.pick(_rules(db), features_of(deal), R.close_date(pf.strftime("%Y-%m")), R.MAIN)


def of_deal(db: Session, deal) -> dict:
    """Действующий СК сделки и откуда он (владелец 27.10.2026: «везде из новых»): `deal` — поправлен на закрытии,
    `rule` — правило «Агентских условий», `none` — не задан. СК юрлица (`counterparties.sk_*`) — история, не читается.
    Ключи `payer_*` — то, что даёт правило (экран сверки показывает «по условиям» рядом с поправкой)."""
    row = db.query(FinalReconDeal).filter(FinalReconDeal.deal_id == deal.id).first()
    payer = payer_of(db, deal)
    rule = rule_of(db, deal)
    base = {"payer_id": getattr(payer, "id", None), "payer_name": getattr(payer, "name", None),
            "payer_mode": rule["mode"] if rule else None, "payer_percent": rule["percent"] if rule else None,
            "rule_id": rule["id"] if rule else None}
    # Строку сверки создаёт и пин суммы ДС (15.10.2026) — СК поправлен на сделке, только если в ней задано хоть что-то по СК,
    # иначе пустая строка перекрывала бы правило.
    if row and (row.sk_mode or row.sk_percent is not None):
        return {**base, "mode": row.sk_mode, "percent": row.sk_percent, "source": "deal"}
    if rule:
        return {**base, "mode": rule["mode"], "percent": rule["percent"], "source": "rule"}
    return {**base, "mode": None, "percent": None, "source": "none"}


def _overrides(db: Session, ids) -> dict:
    ids = list(ids)
    if not ids:
        return {}
    return {r.deal_id: (r.sk_mode, r.sk_percent) for r in db.query(FinalReconDeal).filter(FinalReconDeal.deal_id.in_(ids)).all()
            if r.sk_mode or r.sk_percent is not None}


def _agency_defaults(db: Session) -> dict:
    from app.sales.models import SalesAgency
    return dict(db.query(SalesAgency.id, SalesAgency.sk_percent).all())


AGENCY_DEFAULT_PCT = 30.0     # прежняя константа дашборда продаж — оценка, где у агентства и в правилах ничего нет


def sales_percent_many(db: Session, deals) -> dict:
    """% СК сделок для дашборда продаж (бонусы, «наша сумма») — тем же правилом, что закрытие: поправка сделки, иначе
    правило «Агентских условий»; где правила нет — прежняя оценка `sales_agencies.sk_percent` (30 %), у прямой сделки 0.
    Пакетом: правила и поправки читаются один раз."""
    from app.agency_terms import rules as R
    deals = list(deals)
    rules = _rules(db)
    own = _overrides(db, [d.id for d in deals])
    agency = _agency_defaults(db) if any(d.agency_id for d in deals) else {}
    out = {}
    for d in deals:
        if d.id in own:            # поправка сделки — как на закрытии: действует она, и СК только при способе И проценте
            mode, pct = own[d.id]
            out[d.id] = float(pct) if (mode and pct) else 0.0
            continue
        pf = getattr(d, "period_from", None)
        rule = R.pick(rules, features_of(d), R.close_date(pf.strftime("%Y-%m")), R.MAIN) if pf else None
        if rule:
            out[d.id] = float(rule["percent"])
        elif d.agency_id:
            pct = agency.get(d.agency_id)          # явные 0 % — значение; 30 % — только когда процента нет
            out[d.id] = float(AGENCY_DEFAULT_PCT if pct is None else pct)
        else:
            out[d.id] = 0
    return out


def set_deal(db: Session, deal, mode: Optional[str], percent: Optional[float], user) -> FinalReconDeal:
    validate(mode, percent)
    row = db.query(FinalReconDeal).filter(FinalReconDeal.deal_id == deal.id).first()
    if row is None:
        row = FinalReconDeal(deal_id=deal.id)
        db.add(row)
    row.sk_mode, row.sk_percent = mode, percent
    row.confirmed_at = row.confirmed_by = None     # скидка изменилась — подтверждение сверки снимается
    row.updated_by, row.updated_at = getattr(user, "id", None), datetime.utcnow()
    return row


def set_counterparty(cp: Counterparty, mode: Optional[str], percent: Optional[float]) -> None:
    validate(mode, percent)
    cp.sk_mode, cp.sk_percent = mode, percent
