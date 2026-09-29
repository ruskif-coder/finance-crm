"""Вкладка «Согласования» раздела «Паблишеры»: матрица площадка × РК (владелец 29.09.2026).

Только чтение, своё право `dir_publishers_approvals` (view). Расчёт — app/launch_prep/matrix.py.
"""
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.launch_prep import matrix
from app.models import User
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("dir_publishers_approvals", "view")


@router.get("/matrix")
def get_matrix(month: Optional[str] = None, service_id: Optional[int] = None,
               db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    month = month or date.today().strftime("%Y-%m")
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=400, detail="Месяц — в виде ГГГГ-ММ, например 2026-10")
    return {**matrix.load(db, month, service_id), "months": matrix.months(db)}
