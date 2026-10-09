# -*- coding: utf-8 -*-
"""Вкладка «Аудитория» раздела «Паблишеры» (владелец 09.10.2026). Своё право
`dir_publishers_audience`: view — экран, edit — внесение замеров. Расчёт — app/sales/publisher_audience.py."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.sales import publisher_audience as A
from app.sales.models import SalesPublisher

router = APIRouter()
VIEW = require_permission("dir_publishers_audience", "view")
EDIT = require_permission("dir_publishers_audience", "edit")

MAX_DAYS = 365


class MeasureIn(BaseModel):
    metric: str
    value: float
    source: str
    measured_at: date
    surface_kind: Optional[str] = None
    segment: Optional[str] = None
    note: Optional[str] = None


def _days(days: int) -> int:
    if not 1 <= days <= MAX_DAYS:
        raise HTTPException(400, f"Окно — от 1 до {MAX_DAYS} дней")
    return days


def _pub(db: Session, publisher_id: int) -> SalesPublisher:
    p = db.query(SalesPublisher).filter_by(id=publisher_id).first()
    if not p:
        raise HTTPException(404, "Площадка не найдена")
    return p


@router.get("")
def get_overview(days: int = 30, db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    return A.overview(db, days=_days(days))


@router.get("/sources")
def get_sources(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    return A.sources(db)


class BulkItem(BaseModel):
    publisher_id: int
    key: str
    value: float


class BulkIn(BaseModel):
    source: str
    measured_at: date
    items: List[BulkItem]


MAX_XLSX = 5 * 1024 * 1024


def _check_items(db: Session, items) -> None:
    ids = {i.publisher_id for i in items}
    known = {r[0] for r in db.query(SalesPublisher.id).filter(SalesPublisher.id.in_(ids)).all()}
    if ids - known:
        raise HTTPException(404, f"Площадки не найдены: {sorted(ids - known)}")
    bad = sorted({i.key for i in items if i.key not in A.FIELD_BY_KEY and i.key not in A.SYS_BY_KEY})
    if bad:
        raise HTTPException(400, f"Неизвестные поля: {', '.join(bad)}")


@router.get("/grid")
def get_grid(only_active: bool = True, db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Сетка заполнения — вторая вкладка экрана: площадки × поля, в ячейке последний замер."""
    return A.grid(db, only_active=only_active)


@router.post("/bulk")
def post_bulk(data: BulkIn, db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    """Записать пачку значений сетки одним источником и датой; равные последнему замеру пропускаются."""
    if data.measured_at > date.today():
        raise HTTPException(400, "Дата замера в будущем")
    if not data.items:
        raise HTTPException(400, "Нечего сохранять")
    _check_items(db, data.items)
    try:
        res = A.apply_items(db, [i.dict() for i in data.items], source=data.source,
                            measured_at=data.measured_at, user_id=current_user.id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    log_action(db, current_user, "publisher_audience_bulk", "publisher", None,
               f"{data.source}, {data.measured_at}: записано {res['written']}, площадок {res['publishers']}")
    return res


@router.get("/export.xlsx")
def export_xlsx(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    return Response(content=A.export_xlsx(db),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/import")
async def import_xlsx(apply: bool = False, file: UploadFile = File(...), db: Session = Depends(get_db),
                      current_user: User = Depends(EDIT)):
    """Загрузка книги. apply=false — ПРЕДПРОСМОТР (что запишется, что отклонено), apply=true — запись.
    Значения строки идут с её источником и датой; ошибочные строки отклоняются целиком, остальные пишутся."""
    contents = await file.read()
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Ожидается файл .xlsx")
    if len(contents) > MAX_XLSX:
        raise HTTPException(400, "Файл слишком большой (максимум 5 МБ)")
    try:
        parsed = A.parse_xlsx(db, contents)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # группируем по (источник, дата): одна пачка — один вызов записи
    groups: dict = {}
    for it in parsed["items"]:
        groups.setdefault((it["source"], it["measured_at"]), []).append(it)
    totals = {"written": 0, "skipped_same": 0, "publishers": set()}
    for (src, when), its in groups.items():
        try:
            res = A.apply_items(db, its, source=src, measured_at=when, user_id=current_user.id, commit_rows=apply)
        except ValueError as e:
            parsed["errors"].append(str(e))
            continue
        totals["written"] += res["written"]
        totals["skipped_same"] += res["skipped_same"]
        totals["publishers"] |= {i["publisher_id"] for i in its}
    out = {"applied": apply, "written": totals["written"], "skipped_same": totals["skipped_same"],
           "publishers": len(totals["publishers"]), "errors": parsed["errors"][:30],
           "errors_total": len(parsed["errors"]), "unknown_columns": parsed["unknown_columns"]}
    if apply:
        db.commit()
        log_action(db, current_user, "publisher_audience_import", "publisher", None,
                   f"{file.filename}: записано {out['written']}, ошибок {out['errors_total']}")
    else:
        db.rollback()
    return out


@router.get("/{publisher_id}")
def get_publisher(publisher_id: int, days: int = 30, db: Session = Depends(get_db),
                  current_user: User = Depends(VIEW)):
    _pub(db, publisher_id)
    out = A.overview(db, days=_days(days))
    row = next((p for p in out["publishers"] if p["id"] == publisher_id), None)
    if row is None:
        raise HTTPException(404, "Площадка в архиве — на экране аудитории её нет")
    return {**row, "history": A.history(db, publisher_id), "window": out["window"]}


@router.post("/{publisher_id}/measures")
def add_measure(publisher_id: int, data: MeasureIn, db: Session = Depends(get_db),
                current_user: User = Depends(EDIT)):
    pub = _pub(db, publisher_id)
    if data.value < 0:
        raise HTTPException(400, "Значение не может быть отрицательным")
    if data.measured_at > date.today():
        raise HTTPException(400, "Дата замера в будущем")
    try:
        row = A.add_measure(db, publisher_id, metric=data.metric, value=data.value, source=data.source,
                            measured_at=data.measured_at, surface_kind=data.surface_kind,
                            segment=data.segment, note=data.note, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    log_action(db, current_user, "publisher_audience_add", "publisher", publisher_id,
               f"{pub.name}: {A.METRICS[data.metric]['label']} = {data.value:g} ({data.source}, {data.measured_at})")
    return A._row(row)


@router.delete("/measures/{measure_id}")
def delete_measure(measure_id: int, db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    row = db.query(A.SalesPublisherAudience).filter_by(id=measure_id).first()
    if not row:
        raise HTTPException(404, "Замер не найден")
    pid, label = row.publisher_id, f"{A.METRICS.get(row.metric, {}).get('label', row.metric)} = {float(row.value):g}"
    db.delete(row)
    db.commit()
    log_action(db, current_user, "publisher_audience_delete", "publisher", pid, label)
    return {"ok": True}
