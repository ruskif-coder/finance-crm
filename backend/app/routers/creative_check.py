# -*- coding: utf-8 -*-
"""Страница «Проверка креатива» (аккаунты, 07.10.2026): загрузить баннер, проверить код, получить нацеливание.

Права: секция `creative_check` — просмотр / правка (загрузка и нацеливание) / удаление. Проверка видна
только автору: чужие проверки не открываются ни списком, ни по номеру (404).
Историю не храним: через 48 часов крон `app.creative_check.cleanup` останавливает нацеливание и стирает.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.audit import log_action
from app.creative_check import analyze as az
from app.creative_check import service
from app.creative_check.models import CreativeCheck
from app.database import get_db
from app.models import User
from app.permissions import require_permission

router = APIRouter()

VIEW = require_permission("creative_check", "view")
EDIT = require_permission("creative_check", "edit")
DELETE = require_permission("creative_check", "delete")


def _mine(db: Session, check_id: int, user: User) -> CreativeCheck:
    """Проверка автора; чужая и просроченная — «не найдена» (не подсказываем, что она есть)."""
    chk = db.query(CreativeCheck).filter(CreativeCheck.id == check_id).first()
    if not chk or chk.created_by != user.id or chk.expires_at < datetime.utcnow():
        raise HTTPException(status_code=404, detail="Проверка не найдена или уже удалена по сроку")
    return chk


@router.get("/publishers")
def publishers(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Площадки, на которых нацеливание покажет баннер: наш код и веб, не в архиве."""
    return service.default_publishers(db)


@router.get("")
def my_checks(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    rows = (db.query(CreativeCheck)
            .filter(CreativeCheck.created_by == current_user.id,
                    CreativeCheck.expires_at >= datetime.utcnow())
            .order_by(CreativeCheck.id.desc()).all())
    return [service.view(db, r) for r in rows]


@router.post("")
async def create_check(title: str = Form(...), url: str = Form(...), file: UploadFile = File(...),
                       db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    data = await file.read()
    try:
        chk = service.create(db, current_user, title, url, file.filename or "creative", data)
    except service.CheckInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except az.CheckRejected as e:
        raise HTTPException(status_code=400, detail="; ".join(e.messages))
    log_action(db, current_user, "creative_check_create", "creative_check", chk.id,
               f"«{chk.title}», {chk.kind}, замечаний: {len((chk.verdict or {}).get('warnings', []))}")
    return service.view(db, chk)


@router.post("/{check_id}/targeting-link")
def targeting_link(check_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    """Свежая ссылка нацеливания: демо-ЕРИД и демо-контур, как у первичной проверки трафиков.

    Ссылка не хранится (живёт 48 часов и выпускается по нажатию); выпущенная ссылка НЕ подтверждает,
    что баннер крутится, — это видно по `active` и `reason`."""
    from app.dsp import check_creative
    from app.dsp.client import MsError
    from app.dsp.targeting_creative import TargetingCreativeError
    from app.dsp.targeting_link import TargetingLinkError, issue

    chk = _mine(db, check_id, current_user)
    try:
        live = check_creative.ensure_live(db, chk)
    except (TargetingCreativeError, MsError) as e:
        raise HTTPException(status_code=400, detail=f"Креатив нацеливания не заведён: {e}")
    try:
        link = issue(live["xxhash"])
    except TargetingLinkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    until = f" до {link.expires_at:%d.%m %H:%M} UTC" if link.expires_at else ""
    log_action(db, current_user, "creative_check_targeting", "creative_check", chk.id,
               f"«{chk.title}»: выпущена ссылка нацеливания{until}"
               + ("; креатив крутится" if live["active"] else f"; не крутится: {live['reason']}"))
    return {"url": link.url, "targeting_xxhash": live["xxhash"],
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "active": live["active"], "reason": live["reason"],
            "creative_status": live["creative_status"], "campaign_status": live["campaign_status"],
            "restarted": live["restarted"]}


@router.delete("/{check_id}")
def delete_check(check_id: int, db: Session = Depends(get_db), current_user: User = Depends(DELETE)):
    """Снять проверку: сперва остановить нацеливание в DSP, потом стереть файлы и строку."""
    from app.dsp.targeting_creative import TargetingCreativeError
    chk = _mine(db, check_id, current_user)
    title = chk.title
    try:
        service.delete(db, chk)
    except TargetingCreativeError as e:
        raise HTTPException(status_code=502, detail=f"{e}. Повторите позже — проверка остаётся на месте")
    log_action(db, current_user, "creative_check_delete", "creative_check", check_id, f"«{title}»")
    return {"ok": True}
