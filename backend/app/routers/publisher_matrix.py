"""Вкладка «Согласования» раздела «Паблишеры»: матрица площадка × РК (владелец 29.09.2026).

Только чтение, своё право `dir_publishers_approvals` (view). Расчёт — app/launch_prep/matrix.py.
"""
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.database import get_db
from app.launch_prep import matrix, stuck
from app.launch_prep.models import LaunchPrepCreativeFile, LaunchPrepCreativeSet, LaunchPrepPair
from app.models import User
from app.sales.models import SalesRep
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("dir_publishers_approvals", "view")


@router.get("/matrix")
def get_matrix(month: Optional[str] = None, service_id: Optional[int] = None,
               scope: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    month = month or date.today().strftime("%Y-%m")
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=400, detail="Месяц — в виде ГГГГ-ММ, например 2026-10")
    group = current_user.role.staff_group or ""
    can_mine = True   # переключатель у всех; «мои» зависят от рабочей группы роли
    # Умолчание считает сервер (как на дашборде трафика): рядовому — «мои», мастеру — «все».
    if scope not in ("mine", "all"):
        scope = "mine" if group in ("account", "traffic") and not current_user.role.is_master else "all"
    mine = None
    if can_mine and scope == "mine":
        rep = db.query(SalesRep.id).filter(SalesRep.user_id == current_user.id).first()
        mine = (group, rep[0] if rep else -1)
    else:
        scope = "all"
    return {**matrix.load(db, month, service_id, mine=mine), "months": matrix.months(db),
            "scope": scope, "can_mine": can_mine}


@router.get("/stuck")
def get_stuck(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Вкладка «Подвисшие» — app/launch_prep/stuck.py."""
    return stuck.load(db)


# ── Предпросмотр креатива в «Подвисших» (владелец 29.10.2026) ──────────────────────────────────────
# У менеджера паблишеров нет права на креативы сделки, а смотреть баннер, который подвис на площадке, ему нужно.
# Отдаём только креативы, уже отправленные площадке: их и так видела площадка, а черновики сборки — нет.

def _sent_set(db: Session, set_id: int):
    s = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    sent = s is not None and db.query(exists().where(LaunchPrepPair.set_id == set_id,
                                                     LaunchPrepPair.sent_at.isnot(None))).scalar()
    if not sent:
        raise HTTPException(status_code=404, detail="Креатив не найден")
    return s


@router.get("/set/{set_id}/files")
def set_files(set_id: int, db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    from app.routers.launch_prep import file_json      # роутер сборки тянет полпроекта — лениво
    s = _sent_set(db, set_id)
    files = db.query(LaunchPrepCreativeFile).filter(LaunchPrepCreativeFile.set_id == s.id).order_by(LaunchPrepCreativeFile.id).all()
    return {"id": s.id, "no": s.no, "title": s.title, "files": [file_json(f) for f in files]}


@router.get("/file/{file_id}")
def file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    from app.routers.launch_prep import file_response
    rec = db.query(LaunchPrepCreativeFile).filter(LaunchPrepCreativeFile.id == file_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    _sent_set(db, rec.set_id)
    return file_response(rec)
