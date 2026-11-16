# -*- coding: utf-8 -*-
"""Журнал действий по макету design_handoff_journal (16.11.2026): лента двух контуров и выгрузка в Excel.

Смотреть — по праву «Журнал» (`settings_audit` · view, как и прежний экран); выгружать — только администратор
(решение владельца 16.11.2026: отдельного права «выгрузка» в матрице ролей не заводим). Сама выгрузка пишется в журнал.
Прежняя ручка `/users/audit-log/` остаётся: её зовут другие экраны.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.audit import log_action, require_admin
from app.database import get_db
from app.journal import feed
from app.models import User
from app.permissions import require_permission

router = APIRouter()
CONTOURS = ("staff", "cabinet", "all")


def _query(contour, date_from, date_to, actor, q, section, action, offset=0, limit=200) -> feed.Query:
    if contour not in CONTOURS:
        raise HTTPException(status_code=400, detail="Контур — staff, cabinet или all")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата «с» позже даты «по»")
    return feed.Query(contour=contour, date_from=date_from, date_to=date_to, actor=actor or None, q=q or None,
                      section=section or None, action=action or None, offset=offset, limit=limit)


@router.get("/")
def journal(contour: str = "staff", date_from: Optional[date] = None, date_to: Optional[date] = None,
            actor: Optional[str] = None, q: Optional[str] = None, section: Optional[str] = None,
            action: Optional[str] = None, offset: int = 0, limit: int = 200, db: Session = Depends(get_db),
            current_user: User = Depends(require_permission("settings_audit", "view"))):
    return feed.fetch(db, _query(contour, date_from, date_to, actor, q, section, action, offset, limit))


@router.get("/export")
def journal_export(contour: str = "staff", date_from: Optional[date] = None, date_to: Optional[date] = None,
                   actor: Optional[str] = None, q: Optional[str] = None, section: Optional[str] = None,
                   action: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.doc_names import disposition
    from app.journal import export
    f = _query(contour, date_from, date_to, actor, q, section, action)
    try:
        data, n = export.build(db, f)
    except export.TooMany as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not n:
        raise HTTPException(status_code=400, detail="Нечего выгружать — по фильтрам записей нет")
    filters = ", ".join(f"{k}={v}" for k, v in (("контур", contour), ("с", date_from), ("по", date_to), ("кто", actor),
                                                 ("поиск", q), ("раздел", section), ("действие", action)) if v)
    log_action(db, current_user, "journal_export", entity_type=None, entity_id=None,
               details=f"строк: {n}" + (f"; {filters}" if filters else ""))
    stamp = date.today().isoformat()
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": disposition(f"Журнал действий {stamp}.xlsx", f"journal_{stamp}.xlsx")})
