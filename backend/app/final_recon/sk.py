# -*- coding: utf-8 -*-
"""СК сделки на закрытии (владелец 14.10.2026): у юрлица-плательщика — способ (постоплата / скидка в счёт) и базовый %; на сделке —
свои значения, по умолчанию от плательщика, аккаунт правит. Без способа СК не закрыть Альфарм-Таргет."""
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


def of_deal(db: Session, deal) -> dict:
    """Действующий СК сделки и откуда он: `deal` — поправлен на закрытии, `payer` — от плательщика, `none` — не задан нигде."""
    row = db.query(FinalReconDeal).filter(FinalReconDeal.deal_id == deal.id).first()
    payer = payer_of(db, deal)
    base = {"payer_id": getattr(payer, "id", None), "payer_name": getattr(payer, "name", None),
            "payer_mode": getattr(payer, "sk_mode", None), "payer_percent": getattr(payer, "sk_percent", None)}
    # Строку сверки создаёт и пин суммы ДС (15.10.2026) — СК поправлен на сделке, только если в ней задано хоть что-то по СК,
    # иначе пустая строка перекрывала бы СК плательщика.
    if row and (row.sk_mode or row.sk_percent is not None):
        return {**base, "mode": row.sk_mode, "percent": row.sk_percent, "source": "deal"}
    if payer and (payer.sk_mode or payer.sk_percent is not None):
        return {**base, "mode": payer.sk_mode, "percent": payer.sk_percent, "source": "payer"}
    return {**base, "mode": None, "percent": None, "source": "none"}


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
