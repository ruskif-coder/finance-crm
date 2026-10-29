# -*- coding: utf-8 -*-
"""«Паблишеры → Взаимодействие»: сверки площадок за месяц и сводная (владелец 26.10.2026).

Право — `dir_publishers_interaction` (смотреть / править); бэкфилл — менеджеру паблишеров. Логика —
`app/publisher_recon`, здесь только двери, права и журнал.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.files_safe import existing_upload_path
from app.models import User
from app.permissions import require_permission
from app.publisher_recon import board as B
from app.publisher_recon import razaloc as R
from app.publisher_recon import service as S
from app.publisher_requests import PublisherRequest

router = APIRouter()
VIEW = require_permission("dir_publishers_interaction", "view")
EDIT = require_permission("dir_publishers_interaction", "edit")


def _period(period: str) -> str:
    if not B.period_ok(period):
        raise HTTPException(400, "Месяц — в виде ГГГГ-ММ")
    return period


def _req(db: Session, request_id: int) -> PublisherRequest:
    req = db.get(PublisherRequest, request_id)
    if req is None or req.kind != "сверка":
        raise HTTPException(404, "Сверка не найдена")
    return req


def _label(db: Session, req: PublisherRequest) -> str:
    site = db.execute(text("SELECT coalesce(domain, name) FROM sales_publishers WHERE id = :p"),
                      {"p": req.publisher_id}).scalar()
    return f"{site} · {req.period}"


@router.get("/board")
def board(period: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return B.board(db, _period(period or date.today().strftime("%Y-%m")))


@router.get("/summary")
def summary(year: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    year = year or date.today().year
    if not 2020 <= year <= 2100:
        raise HTTPException(400, "Год вне диапазона")
    return B.summary(db, year)


@router.get("/detail")
def detail(publisher_id: int, period: str, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    out = B.detail(db, publisher_id, _period(period))
    if out is None:
        raise HTTPException(404, "У площадки нет размещений за этот месяц")
    rid = out["row"]["request_id"]
    if rid:
        S.mark_seen(_req(db, rid), "мы")
        db.commit()
    return out


class SendIn(BaseModel):
    publisher_id: int
    period: str


@router.post("/send")
def send(payload: SendIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    try:
        req = S.send(db, payload.publisher_id, _period(payload.period), user)
    except S.ReconError as e:
        raise HTTPException(e.status, e.message)
    log_action(db, user, "publisher_recon_send", "publisher_request", req.id, f"{_label(db, req)}: сверка отправлена")
    db.commit()
    return {"request_id": req.id}


class PeriodIn(BaseModel):
    period: str


@router.post("/send-all")
def send_all(payload: PeriodIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    try:
        reqs = S.send_all(db, _period(payload.period), user)
    except S.ReconError as e:
        raise HTTPException(e.status, e.message)
    for req in reqs:
        log_action(db, user, "publisher_recon_send", "publisher_request", req.id, f"{_label(db, req)}: сверка отправлена")
    db.commit()
    return {"sent": len(reqs)}


@router.post("/{request_id}/reply")
async def reply(request_id: int, body: str = Form(""), volume: Optional[int] = Form(None),
                file: Optional[UploadFile] = File(None), db: Session = Depends(get_db), user: User = Depends(EDIT)):
    req = _req(db, request_id)
    try:
        m = S.reply(db, req, user, body, volume)
        if file is not None and file.filename:
            S.save_file(db, m, file.filename, file.content_type, await file.read(S.FILE_MAX + 1))
    except S.ReconError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    log_action(db, user, "publisher_recon_reply", "publisher_request", req.id,
               f"{_label(db, req)}: ответ площадке" + (f", предложено {volume}" if volume is not None else ""))
    db.commit()
    return {"message_id": m.id}


@router.post("/{request_id}/remind")
def remind(request_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    req = _req(db, request_id)
    try:
        S.remind(db, req)
    except S.ReconError as e:
        raise HTTPException(e.status, e.message)
    log_action(db, user, "publisher_recon_remind", "publisher_request", req.id, f"{_label(db, req)}: напомнили")
    db.commit()
    return {"ok": True}


class AgreeIn(BaseModel):
    volume: int


@router.post("/{request_id}/agree")
def agree(request_id: int, payload: AgreeIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    req = _req(db, request_id)
    try:
        S.agree(db, req, user, payload.volume)
    except S.ReconError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    rc = req.recon
    log_action(db, user, "publisher_recon_agree", "publisher_request", req.id,
               f"{_label(db, req)}: итог {payload.volume} (наши {rc.our_volume}, площадки {rc.their_volume})")
    db.commit()
    return {"status": B.DONE}


@router.get("/{request_id}/razaloc")
def razaloc(request_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Разаллокация согласованной сверки для экрана: строки по договорам ОРД и сделки, которым договора не хватает."""
    req = _req(db, request_id)
    if req.verdict != B.AGREED:
        raise HTTPException(409, "Разаллокация появится после согласования сверки")
    return R.of_request(db, req)


@router.get("/{request_id}/razaloc.xlsx")
def razaloc_xlsx(request_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return R.response(db, [_req(db, request_id)])


@router.get("/file/{file_id}")
def file(file_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    f = db.execute(text("SELECT path, original_name FROM publisher_request_file WHERE id = :f"),
                   {"f": file_id}).first()
    if f is None:
        raise HTTPException(404, "Файл не найден")
    return FileResponse(existing_upload_path(f.path, subdir=S.FILE_DIR), filename=f.original_name or "file")
