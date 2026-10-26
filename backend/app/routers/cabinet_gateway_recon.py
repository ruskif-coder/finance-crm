# -*- coding: utf-8 -*-
"""Шлюз кабинета для сверки месяца (26.10.2026): ответ площадки, «прочитано», вложение, скачать файл.

Кабинет в базу не пишет — читает `pub.recon_*_v1`, а меняет через ядро (как креативы и приоритезация).
Монтируется под тем же префиксом `/api/cabinet-gw`, закрытым на Caddy.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cabinet import journal
from app.database import get_db
from app.files_safe import existing_upload_path
from app.publisher_recon import service as S
from app.publisher_requests import PublisherRequest
from app.routers.cabinet_gateway import _actor, require_cabinet_service

router = APIRouter()


def _recon(db: Session, request_id: int, publisher_id: int) -> PublisherRequest:
    req = db.get(PublisherRequest, request_id)
    # Площадка — из самой сверки: подставленная снаружи открыла бы чужую.
    if req is None or req.kind != "сверка" or req.publisher_id != publisher_id:
        raise HTTPException(404, "Сверка не найдена")
    return req


def _subject(req: PublisherRequest) -> str:
    return f"Сверка · {req.period}"


# Вид ответа → событие журнала кабинета.
KINDS = {"согласен": 'сверка_согласие', "расхождение": 'сверка_расхождение', "сообщение": 'сверка_сообщение'}


class AnswerIn(BaseModel):
    publisher_id: int
    account_id: int
    kind: str                       # согласен | расхождение | сообщение
    volume: Optional[int] = None
    body: Optional[str] = None
    author_name: str
    author_email: Optional[str] = None


@router.post("/recon/{request_id}/answer", dependencies=[Depends(require_cabinet_service)])
def answer(request_id: int, payload: AnswerIn, db: Session = Depends(get_db)):
    """«Согласен с N», «Есть расхождение» (своя цифра обязательна) или сообщение в переписку. Итог фиксирует
    менеджер паблишеров."""
    if payload.kind not in KINDS:
        raise HTTPException(400, "Неизвестный ответ")
    req = _recon(db, request_id, payload.publisher_id)
    acc = _actor(db, payload.account_id, payload.publisher_id, approve=True)
    try:
        m = S.publisher_answer(db, req, payload.author_name, payload.author_email, payload.kind == "согласен",
                               payload.volume, payload.body, free=payload.kind == "сообщение")
    except S.ReconError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    journal.write(db, KINDS[payload.kind], cabinet_id=acc.cabinet_id,
                  account_id=acc.id, publisher_id=payload.publisher_id, actor_name=payload.author_name,
                  subject=_subject(req), entity_type='publisher_request', entity_id=req.id)
    db.commit()
    return {"message_id": m.id, "volume": m.volume}


class SeenIn(BaseModel):
    publisher_id: int
    account_id: int


@router.post("/recon/{request_id}/seen", dependencies=[Depends(require_cabinet_service)])
def seen(request_id: int, payload: SeenIn, db: Session = Depends(get_db)):
    """Площадка открыла переписку — счётчик нового ответа гаснет."""
    req = _recon(db, request_id, payload.publisher_id)
    _actor(db, payload.account_id, payload.publisher_id)
    S.mark_seen(req, "площадка")
    db.commit()
    return {"ok": True}


@router.post("/recon/{request_id}/file", dependencies=[Depends(require_cabinet_service)])
async def upload(request_id: int, publisher_id: int, account_id: int, message_id: int,
                 file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Файл статистики площадки — к её же сообщению этой сверки."""
    req = _recon(db, request_id, publisher_id)
    _actor(db, account_id, publisher_id, approve=True)
    from app.publisher_requests import PublisherRequestMessage
    m = db.get(PublisherRequestMessage, message_id)
    if m is None or m.request_id != req.id or m.side != "площадка":
        raise HTTPException(404, "Сообщение не найдено")
    try:
        f = S.save_file(db, m, file.filename, file.content_type, await file.read(S.FILE_MAX + 1))
    except S.ReconError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    db.commit()
    return {"id": f.id, "name": f.original_name, "size_bytes": f.size_bytes}


@router.get("/recon/{request_id}/file/{file_id}", dependencies=[Depends(require_cabinet_service)])
def download(request_id: int, file_id: int, publisher_id: int, account_id: int, db: Session = Depends(get_db)):
    req = _recon(db, request_id, publisher_id)
    _actor(db, account_id, publisher_id)
    f = db.execute(text("""SELECT f.path, f.original_name FROM publisher_request_file f
                            JOIN publisher_request_message m ON m.id = f.message_id
                           WHERE f.id = :f AND m.request_id = :r"""), {"f": file_id, "r": req.id}).first()
    if f is None:
        raise HTTPException(404, "Файл не найден")
    return FileResponse(existing_upload_path(f.path, subdir=S.FILE_DIR), filename=f.original_name or "file")
