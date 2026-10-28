# -*- coding: utf-8 -*-
"""Сводка карточки контрагента v2 (хендофф «контрикZ», 28.10.2026): `GET /api/counterparties/{id}/overview`, право «Контрагенты →
просмотр». Отдельный роутер: `counterparties.py` и так 1000+ строк. Логика — `app/counterparty_card/service.py`."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.counterparty_card import service as CS
from app.database import get_db
from app.models import Counterparty, User
from app.permissions import require_permission

router = APIRouter()


@router.get("/{counterparty_id}/overview")
def counterparty_overview(counterparty_id: int, db: Session = Depends(get_db),
                          user: User = Depends(require_permission("counterparties", "view"))):
    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(404, "Контрагент не найден")
    return CS.overview(db, cp, user)
