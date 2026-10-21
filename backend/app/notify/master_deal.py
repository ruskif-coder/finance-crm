# -*- coding: utf-8 -*-
"""«Вашу сделку забрали в пакет» (владелец 16.10.2026).

Мастер-сделка собирается из сделок одного договора и месяца, и они могут принадлежать разным
аккаунтам: кто собирает пакет, решается на распределении. Если сделку в пакет добавил не её
аккаунт — аккаунту и мастерам аккаунтов уходит событие `deal_taken_into_master` (канал —
дайджест). Своя сделка своим аккаунтом — тишина."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger("finance.master_deal")


def _owner_user_id(db: Session, deal) -> Optional[int]:
    from app.sales.models import SalesRep
    if not deal.account_manager_id:
        return None
    rep = db.get(SalesRep, deal.account_manager_id)
    return rep.user_id if rep else None


def _emit(db: Session, deal, m, user) -> None:
    from app.notify.bus import emit
    from app.sales.deal_label import deal_label
    who = getattr(user, "name", None) or getattr(user, "email", "") or "кто-то"
    emit(db, "deal_taken_into_master", title=f"{deal_label(deal)} — в пакете {m.code}",
         body=f"Вашу сделку {deal.code} добавил(а) в мастер-сделку {m.code}: {who}.",
         link=f"/accounts/master/{m.code}", entity_type="sales_deal", entity_id=deal.id,
         actor=user, ctx={"deal": deal}, code=deal.code)


def deal_taken(db: Session, deal, m, user) -> None:
    """Сбой уведомления не роняет сборку пакета — пакет важнее письма."""
    if getattr(user, "id", None) is None or _owner_user_id(db, deal) == user.id:
        return
    try:
        _emit(db, deal, m, user)
    except Exception:  # noqa: BLE001
        log.exception("пакет %s: уведомление о сделке %s не ушло", m.code, deal.code)
