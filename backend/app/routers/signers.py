# -*- coding: utf-8 -*-
"""Подписанты (владелец 28.10.2026): список подписантов юрлица — право «Контрагенты» (просмотр / правка); выбор подписанта стороны
договора — право «Договоры → правка». Логика — в `app/signers/service.py`."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import Contract, Counterparty, User
from app.permissions import require_permission
from app.signers import service as S

router = APIRouter()
CP_VIEW = require_permission("counterparties", "view")
CP_EDIT = require_permission("counterparties", "edit")
CONTRACT_EDIT = require_permission("contracts", "edit")


class SignerIn(BaseModel):
    director_name: Optional[str] = None
    signer_position: Optional[str] = None
    signer_basis: Optional[str] = None
    valid_until: Optional[date] = None


class OnIn(BaseModel):
    on: bool = True


class ChooseIn(BaseModel):
    signer_id: Optional[int] = None       # пусто — подписант юрлица по умолчанию


def out(s) -> dict:
    return {"id": s.id, "counterparty_id": s.counterparty_id, "director_name": s.director_name, "signer_position": s.signer_position,
            "signer_basis": s.signer_basis, "valid_until": s.valid_until, "is_default": bool(s.is_default),
            "is_archived": bool(s.is_archived)}


def _run(db: Session, fn):
    try:
        res = fn()
        db.commit()
        return res
    except S.SignerError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)


def _label(s) -> str:
    return f"{s.director_name or '—'} ({s.signer_position or 'без должности'}, {s.signer_basis or 'без основания'})"


@router.get("/counterparty/{cp_id}")
def list_signers(cp_id: int, db: Session = Depends(get_db), user: User = Depends(CP_VIEW)):
    return {"items": [out(s) for s in S.list_of(db, cp_id, archived=True)]}


@router.post("/counterparty/{cp_id}", status_code=201)
def add_signer(cp_id: int, payload: SignerIn, db: Session = Depends(get_db), user: User = Depends(CP_EDIT)):
    if not db.query(Counterparty.id).filter(Counterparty.id == cp_id).first():
        raise HTTPException(404, "Контрагент не найден")
    s = _run(db, lambda: S.create(db, cp_id, payload.dict(), user))
    log_action(db, user, "signer_create", "counterparty", cp_id, _label(s) + (" · по умолчанию" if s.is_default else ""))
    return out(s)


@router.put("/{signer_id}")
def edit_signer(signer_id: int, payload: SignerIn, db: Session = Depends(get_db), user: User = Depends(CP_EDIT)):
    s = _run(db, lambda: S.update(db, signer_id, payload.dict(exclude_unset=True), user))
    log_action(db, user, "signer_update", "counterparty", s.counterparty_id, _label(s))
    return out(s)


@router.put("/{signer_id}/default")
def make_default(signer_id: int, db: Session = Depends(get_db), user: User = Depends(CP_EDIT)):
    s = _run(db, lambda: S.set_default(db, signer_id, user))
    log_action(db, user, "signer_default", "counterparty", s.counterparty_id, _label(s))
    return out(s)


@router.put("/{signer_id}/archive")
def archive(signer_id: int, payload: OnIn, db: Session = Depends(get_db), user: User = Depends(CP_EDIT)):
    s = _run(db, lambda: S.archive(db, signer_id, payload.on, user))
    log_action(db, user, "signer_archive", "counterparty", s.counterparty_id, _label(s) + (" → в архив" if payload.on else " → из архива"))
    return out(s)


@router.put("/contract/{contract_id}/{side}")
def choose(contract_id: int, side: str, payload: ChooseIn, db: Session = Depends(get_db), user: User = Depends(CONTRACT_EDIT)):
    """Подписант стороны договора («заказчик» / «исполнитель»); пусто — подписант юрлица по умолчанию."""
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    s = _run(db, lambda: S.choose(db, c, side, payload.signer_id, user))
    log_action(db, user, "contract_signer", "contract", c.id, f"{side}: " + (_label(s) if s else "подписант по умолчанию"))
    return {"side": side, "signer_id": s.id if s else None}
