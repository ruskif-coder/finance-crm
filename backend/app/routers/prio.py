# -*- coding: utf-8 -*-
"""Приоритезация — сборка в карточке сделки (владелец 19.10.2026). Собирает аккаунт; права — реестр сделок (как сверка),
область видимости — как у сделки. Ответы площадки идут через шлюз кабинета (`cabinet_gw`), не сюда."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.prio import launch as L
from app.prio import models as M
from app.prio import service as S
from app.routers.final_recon import _deal

router = APIRouter()
VIEW = require_permission("sales_registry", "view")
EDIT = require_permission("sales_registry", "edit")


def _err(e: S.PrioError):
    raise HTTPException(e.status, e.message)


@router.get("/deal/{deal_id}")
def prio_view(deal_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return S.view(db, _deal(db, deal_id, user))


@router.get("/publishers")
def prio_publishers(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Площадки для «+ площадка»: активные, site_id системы приоритезации — справочно (без него не отправить)."""
    rows = db.execute(text("""SELECT id, name, prio_site_id FROM sales_publishers
                               WHERE is_active AND coalesce(status, '') <> 'АРХИВ' ORDER BY name""")).all()
    return [{"id": r[0], "name": r[1], "site_id": r[2]} for r in rows]


class CommonIn(BaseModel):
    product_name: Optional[str] = None
    erid_meta: Optional[str] = None
    target_competitors: Optional[str] = None
    target_mnn: Optional[str] = None
    target_meta: Optional[str] = None


@router.put("/deal/{deal_id}/common")
def prio_save_common(deal_id: int, payload: CommonIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    d = _deal(db, deal_id, user)
    try:
        S.save_common(db, d, payload.dict(exclude_unset=True), user)
    except S.PrioError as e:
        db.rollback(); _err(e)
    db.commit()
    log_action(db, user, "prio_common", "sales_deal", d.id, f"{d.code}: общая часть запроса на приоритезацию")
    return S.view(db, d)


class AddIn(BaseModel):
    publisher_id: int


@router.post("/deal/{deal_id}/placements")
def prio_add(deal_id: int, payload: AddIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    d = _deal(db, deal_id, user)
    try:
        p = S.add_placement(db, d, payload.publisher_id, user)
    except S.PrioError as e:
        db.rollback(); _err(e)
    db.commit()
    log_action(db, user, "prio_placement_add", "sales_deal", d.id, f"{d.code}: + площадка {p.publisher_id}")
    return S.view(db, d)


@router.delete("/deal/{deal_id}/placements/{pid}")
def prio_remove(deal_id: int, pid: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    d = _deal(db, deal_id, user)
    try:
        S.remove_placement(db, d, pid)
    except S.PrioError as e:
        db.rollback(); _err(e)
    db.commit()
    log_action(db, user, "prio_placement_remove", "sales_deal", d.id, f"{d.code}: − площадка запроса {pid}")
    return S.view(db, d)


class EditIn(BaseModel):
    product_url: Optional[str] = None
    erid: Optional[str] = None


@router.put("/deal/{deal_id}/placements/{pid}")
def prio_edit(deal_id: int, pid: int, payload: EditIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    d = _deal(db, deal_id, user)
    try:
        S.edit_placement(db, d, pid, payload.dict(exclude_unset=True))
    except S.PrioError as e:
        db.rollback(); _err(e)
    db.commit()
    log_action(db, user, "prio_placement_edit", "sales_deal", d.id,
               f"{d.code}: площадка запроса {pid} — " + ", ".join(payload.dict(exclude_unset=True)))
    return S.view(db, d)


class ActIn(BaseModel):
    text: Optional[str] = None


ACTIONS = {"send": "отправлено площадке", "remind": "напоминание площадке", "reply": "ответ площадке",
           "launch": "запущено", "stop": "остановлено", "start": "возобновлено"}


def _notify(db, d, pid, action):
    """После коммита: письмо площадке может откатить сессию при сбое — действие к этому моменту уже записано."""
    from app.notify import prio as N
    p = db.get(M.PrioPlacement, pid)
    if action in ("send", "remind", "reply"):
        N.request_to_site(db, d, p, {"send": "новый", "remind": "напоминание", "reply": "ответ"}[action])
    elif action in ("launch", "start", "stop"):
        N.live_to_site(db, d, p, action != "stop")


def _act(db, d, pid, action, body, user):
    if action == "send":
        return S.send(db, d, pid, user)
    if action == "remind":
        return S.remind(db, d, pid, user)
    if action == "reply":
        return S.reply(db, d, pid, body.text, user)
    if action == "launch":
        return L.launch(db, d, pid)
    if action in ("stop", "start"):
        return L.toggle(db, d, pid, action == "start")
    raise S.PrioError(400, "Неизвестное действие")


@router.post("/deal/{deal_id}/placements/{pid}/{action}")
def prio_action(deal_id: int, pid: int, action: str, body: ActIn = ActIn(), db: Session = Depends(get_db),
                user: User = Depends(EDIT)):
    d = _deal(db, deal_id, user)
    try:
        _act(db, d, pid, action, body, user)
    except S.PrioError as e:
        db.rollback(); _err(e)
    db.commit()
    _notify(db, d, pid, action)
    log_action(db, user, f"prio_{action}", "sales_deal", d.id, f"{d.code}: площадка запроса {pid} — {ACTIONS.get(action, action)}")
    return S.view(db, d)


@router.post("/deal/{deal_id}/bulk/{action}")
def prio_bulk(deal_id: int, action: str, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """«Отправить площадкам» — все ГОТОВЫЕ черновики; «Запустить согласованные». Отказ по одной строке не роняет остальные."""
    d = _deal(db, deal_id, user)
    if action not in ("send", "launch"):
        raise HTTPException(400, "Массово: send / launch")
    st = S.view(db, d)
    ids = [x["id"] for x in st["placements"]
           if (action == "send" and x["status"] == M.DRAFT and not x["missing"]) or (action == "launch" and x["status"] == M.APPROVED)]
    done, failed = [], []
    for pid in ids:
        try:
            _act(db, d, pid, action, ActIn(), user)
            db.commit()
            _notify(db, d, pid, action)
            done.append(pid)
        except S.PrioError as e:
            db.rollback()
            failed.append({"id": pid, "error": e.message})
    if done:
        log_action(db, user, f"prio_bulk_{action}", "sales_deal", d.id, f"{d.code}: {ACTIONS[action]} — {len(done)} площадок")
    return {**S.view(db, d), "done": done, "failed": failed}
