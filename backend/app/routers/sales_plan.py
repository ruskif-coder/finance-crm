# -*- coding: utf-8 -*-
"""«План продаж» — экран целей и выполнения (владелец 24.10.2026, docs/ПЛАН_план_продаж.md). Расчёт — app/sales/plan.py.

Право `sales_plan`: смотреть — продажи и руководство, править цели — роли с «правкой» (руководитель продаж). Область
«свои/все» — от строки права: «свои» видят общую цель и свою строку продажника."""
from typing import List

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.sales import plan
from app.sales.scope import own_rep_ids_or_all

router = APIRouter()
VIEW = require_permission("sales_plan", "view")
EDIT = require_permission("sales_plan", "edit")


def _year(y: int) -> int:
    if not 2000 <= y <= 2100:
        raise HTTPException(400, "Год вне допустимого диапазона")
    return y


def _own(db, user):
    own = own_rep_ids_or_all(db, user, "sales_plan")
    return None if own is None else list(own)


@router.get("")
def screen(year: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Строки плана года: цели по месяцам и выполнение (факт, в работе, планируемые), прогноз неделю назад."""
    out = plan.screen(db, _year(year), own=_own(db, user))
    from app.permissions import get_permissions_for_user
    out["can_edit"] = user.role.key == "admin" or bool((get_permissions_for_user(db, user).get("sales_plan") or {}).get("edit"))
    return out


@router.get("/weeks")
def weeks(year: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Прогноз года (общая цель) по неделям — для виджета «Прогноз по неделям»; копится с первого ночного снимка."""
    from app.timez import msk_now
    return {"weeks": plan.weekly(db, _year(year), msk_now().date())}


@router.get("/cell")
def cell(year: int, m_from: int, m_to: int, scope: str, key_id: int = 0,
         db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Ячейка: сделки за этим числом, что может закрыть разрыв, история цели."""
    if not 1 <= m_from <= m_to <= 12:
        raise HTTPException(400, "Месяцы — от 1 до 12, начало не позже конца")
    return plan.cell(db, _year(year), m_from, m_to, scope, key_id, own=_own(db, user))


class TargetsIn(BaseModel):
    year: int
    items: List[plan.TargetItem]


@router.put("/targets")
def save_targets(payload: TargetsIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Цели пачкой; пустое значение снимает цель. Каждая правка — в журнал «было → стало»."""
    if len(payload.items) > 2000:
        raise HTTPException(400, "Слишком много целей за раз")
    n = plan.save_targets(db, _year(payload.year), payload.items, user)
    return {"changed": n, **plan.screen(db, payload.year, own=_own(db, user))}


@router.get("/export.xlsx")
def export_xlsx(year: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Цели года шаблоном для правки и лист выполнения. «Свои» выгружают только видимые им строки."""
    from app.sales import plan_xlsx
    body = plan_xlsx.export(db, _year(year), own=_own(db, user))
    human = f"План продаж {year}.xlsx"
    return Response(content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"sales_plan_{year}.xlsx\"; filename*=UTF-8''{quote(human)}"})


@router.post("/import")
async def import_xlsx(year: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Что изменится из загруженного файла — ничего не пишет; применяет экран через PUT /targets."""
    from app.sales import plan_xlsx
    body = await file.read(plan_xlsx.MAX_BYTES + 1)
    return plan_xlsx.preview(db, _year(year), body)
