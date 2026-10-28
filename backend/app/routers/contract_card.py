# -*- coding: utf-8 -*-
"""Карточка договора (владелец 28.10.2026): `GET /api/contracts/{id}/card`. Право — «Договоры → просмотр»; блоки внутри — по правам
своих разделов (`app/contract_card/service.py`). Отдельный роутер: `contracts.py` и так 800+ строк."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.contract_card import service as CC
from app.database import get_db
from app.models import Contract, User
from app.permissions import require_permission

router = APIRouter()


@router.get("/{contract_id}/card")
def contract_card(contract_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("contracts", "view"))):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    return CC.card(db, c, user)
