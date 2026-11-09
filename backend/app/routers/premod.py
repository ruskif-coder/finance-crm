# -*- coding: utf-8 -*-
"""«Трафики → Премодерация» (07.11.2026, экран по макету 08.11): очередь креативов SSP пакетами и наше согласование.

Права: `traffic_premod` — просмотр / правка (решение). Решения в SSP НЕ отправляются (владелец 07.11).
Очередь заполняет крон `app.premod.sync`; ручки здесь только читают её и пишут наши решения.
"""
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import get_permissions_for_user, require_permission
from app.premod import board as B
from app.premod import service, ssp
from app.premod.models import APPROVED, DECLINED

router = APIRouter()
log = logging.getLogger("premod")

VIEW = require_permission("traffic_premod", "view")
EDIT = require_permission("traffic_premod", "edit")
VERDICT_IN = {"approved": APPROVED, "declined": DECLINED}

_REASONS_TTL = 3600
_reasons_cache = {"at": 0.0, "items": None}


def _reason_tree() -> List[dict]:
    """Дерево причин отказа SSP. Меняется редко — держим час в памяти процесса; сбой SSP — пустой список."""
    if _reasons_cache["items"] is None or time.time() - _reasons_cache["at"] > _REASONS_TTL:
        try:
            _reasons_cache.update(at=time.time(), items=ssp.fetch_reasons())
        except ssp.SspError as e:
            log.warning("премодерация: причины отказа не получены: %s", e)
            return _reasons_cache["items"] or []
    return _reasons_cache["items"]


@router.get("/count")
def count(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Неразобранные пакеты — только число, для индикатора в меню."""
    return {"waiting": service.waiting_count(db)}


@router.get("/board")
def board(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Весь экран одним ответом; контракт — `sampleData.js` макета."""
    can_decide = get_permissions_for_user(db, current_user)["traffic_premod"]["edit"]
    return B.board(db, can_decide, _reason_tree())


class DecisionIn(BaseModel):
    verdict: str
    request_ids: List[int]
    reason_code: Optional[int] = None
    comment: Optional[str] = None


def _reason_label(code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    for group in B.reasons_out(_reason_tree()):
        for item in group["items"]:
            if item["code"] == code:
                return item["label"]
    raise HTTPException(status_code=400, detail="Такой причины отказа у SSP нет — обновите страницу")


def _decision_view(db: Session, made, package_id: int) -> dict:
    names = service.user_names(db, [d.decided_by for d in made])
    return B.decision_out(made, names, {made[0].image_hash: package_id})


@router.post("/packages/{package_id}/decision")
def decision(package_id: int, payload: DecisionIn, db: Session = Depends(get_db),
             current_user: User = Depends(EDIT)):
    verdict = VERDICT_IN.get(payload.verdict)
    if verdict is None:
        raise HTTPException(status_code=400, detail="Решение — approved или declined")
    label = _reason_label(payload.reason_code) if verdict == DECLINED else None
    try:
        made = service.decide(db, current_user, package_id, verdict, payload.request_ids,
                              payload.reason_code, label, payload.comment)
    except service.DecisionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(db, current_user, "premod_decide", "premod_package", package_id,
               f"{verdict}: заявок {len(made)}" + (f", причина {label}" if label else ""))
    db.commit()
    return _decision_view(db, made, package_id)


class BulkIn(BaseModel):
    package_ids: List[int]


@router.post("/bulk-approve")
def bulk_approve(payload: BulkIn, db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    """«Одобрить чистые»: пакеты без нарушений разом. Хоть один с нарушением — 409, не пишется ничего."""
    try:
        made = service.bulk_approve(db, current_user, payload.package_ids)
    except service.NotClean as e:
        db.rollback()
        return JSONResponse(status_code=409, content={"detail": str(e), "missing": e.missing})
    except service.DecisionError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    for package_id, decisions in zip(payload.package_ids, made):
        log_action(db, current_user, "premod_decide", "premod_package", package_id,
                   f"{APPROVED} разом («Одобрить чистые»): заявок {len(decisions)}")
    db.commit()
    return [_decision_view(db, d, i) for i, d in zip(payload.package_ids, made)]


class CategoryIn(BaseModel):
    category: Optional[str] = None


@router.patch("/advertisers/{inn}")
def set_category(inn: str, payload: CategoryIn, db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    """Категория заказчика премодерации; проверки его пакетов пересчитываются сразу."""
    try:
        service.set_category(db, inn, payload.category)
    except service.UnknownAdvertiser as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, current_user, "premod_category", "premod_advertiser", None,
               f"ИНН {inn}: категория «{(payload.category or '').strip() or 'не задана'}»")
    db.commit()
    return {"ok": True}
