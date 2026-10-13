# -*- coding: utf-8 -*-
"""Страница «Отчёт по РК» (трафик, владелец 11.10.2026). Право — своё, `rk_report` (view; с 13.10.2026:
владелец раздаёт его по ролям, в том числе аккаунтам — кнопка в расхлопе их дашборда ведёт сюда же);
деньги видны по этому праву (решение владельца). Область видимости РК — та же, что у дашборда.
Данные — `app/ad/rk_analysis.py`, расчёты — на странице (`frontend/lib/rkAnalysis.mjs`)."""
import re
from datetime import date
from typing import List, Optional, Union
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ad import rk_analysis as A
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.routers.traffic_dashboard import _campaign_in_scope

router = APIRouter()
VIEW = require_permission("rk_report", "view")


@router.get("/{code}")
def page(code: str, prev_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    if not re.fullmatch(r"[A-Za-z0-9]{1,12}", code or ""):
        raise HTTPException(400, "Код сделки — латиница и цифры")
    head = A.head_of(db, code)
    if head is None:
        raise HTTPException(404, f"РК сделки {code} не найдена")
    _campaign_in_scope(db, head["id"], user)
    dsp_db = None
    try:
        from app.dsp.db import DspSessionLocal
        dsp_db = DspSessionLocal() if DspSessionLocal else None
        return A.build(db, head, dsp_db=dsp_db, prev_id=prev_id)
    finally:
        if dsp_db is not None:
            dsp_db.close()


class Column(BaseModel):
    key: str
    label: str


class ExportIn(BaseModel):
    title: str
    columns: List[Column]
    rows: List[dict]


@router.post("/{code}/export.xlsx")
def export(code: str, payload: ExportIn, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Текущий срез страницы в Excel — ровно то, что человек видит в таблице."""
    head = A.head_of(db, code) if re.fullmatch(r"[A-Za-z0-9]{1,12}", code or "") else None
    if head is None:
        raise HTTPException(404, f"РК сделки {code} не найдена")
    _campaign_in_scope(db, head["id"], user)
    if not payload.columns or len(payload.columns) > A.MAX_COLS:
        raise HTTPException(400, f"Колонок должно быть от 1 до {A.MAX_COLS}")
    if len(payload.rows) > A.MAX_ROWS:
        raise HTTPException(400, f"Строк больше {A.MAX_ROWS} — сузьте срез")
    rows = [{c.key: _cell(r.get(c.key)) for c in payload.columns} for r in payload.rows]
    body = A.export_xlsx(payload.title, [c.dict() for c in payload.columns], rows)
    safe = re.sub(r"[^\w-]", "", head["code"] or "")
    human = f"Отчёт_по_РК_{safe}_{date.today():%d.%m.%Y}.xlsx"
    return Response(content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"rk_{safe}.xlsx\"; filename*=UTF-8''{quote(human)}"})


def _cell(v) -> Union[str, float, int, None]:
    """Только числа и короткий текст: в выгрузку не попадают формулы и объекты (защита — ещё и в save_workbook)."""
    if v is None or isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return str(v)[:500]
