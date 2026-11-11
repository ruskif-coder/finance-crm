# -*- coding: utf-8 -*-
"""«Аккаунты → ОРД → Отчёты» (владелец 11.11.2026): отчёт ОРД за месяц — таблица, выгрузка в Excel, импорт правок, снимок ЕРИД.
Права — существующее «ord»: просмотр — смотреть и выгружать; редактирование — загружать, сбрасывать правки, снимать ЕРИД."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.ord import month_report as MR
from app.ord import month_report_store as ST
from app.ord import month_report_xlsx as MX
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("ord", "view")
EDIT = require_permission("ord", "edit")
MAX_FILE = 10 * 1024 * 1024


def _month(s: str):
    try:
        return ST.parse_month(s)
    except MR.ReportError as e:
        raise HTTPException(400, str(e))


def _summary(rows: list) -> dict:
    upds = {(r.get("master_code"), r.get("upd_no"), r.get("kit_no")): r.get("upd_gross") or 0 for r in rows}
    return {"rows": len(rows), "deals": len({r["deal_code"] for r in rows}), "shows": sum(int(r.get("shows") or 0) for r in rows),
            "amount": round(sum(float(r.get("amount") or 0) for r in rows), 2), "upds": len(upds),
            "no_upd": sum(1 for k in upds if k[1] is None), "flagged": sum(1 for r in rows if r.get("note"))}


@router.get("/months")
def report_months(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return ST.months(db)


@router.get("/{month}")
def report_month(month: str, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    m = _month(month)
    rows = ST.report(db, m)
    return {"month": month, "rows": rows, "summary": _summary(rows), "overrides": ST.meta(db, m)}


@router.get("/{month}/xlsx")
def report_xlsx(month: str, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    m = _month(month)
    name = f"ОРД отчёт {m:%m.%Y}.xlsx"
    return Response(content=MX.to_xlsx(ST.report(db, m), m),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"ord_report.xlsx\"; filename*=UTF-8''{quote(name)}"})


@router.post("/{month}/import")
async def report_import(month: str, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(EDIT)):
    m = _month(month)
    data = await file.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise HTTPException(413, "Файл больше 10 МБ")
    try:
        counts = ST.import_file(db, m, MX.parse_xlsx(data), user.id, file.filename)
    except MR.ReportError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except DataError:
        # длинную строку расчёта (несколько ЕРИД одной площадки) правка копирует в колонку — база не примет; не 500
        db.rollback()
        raise HTTPException(400, "Значение в файле не помещается в отчёт — проверьте длинные ЕРИД и номера")
    db.commit()
    log_action(db, user, "ord_report_import", "ord_report", None,
               f"Отчёт ОРД {m:%m.%Y}: загружен «{file.filename}» — правок {counts['правка']}, добавлено {counts['добавлена']}, "
               f"убрано {counts['убрана']}")
    return counts


@router.delete("/{month}/overrides")
def report_reset(month: str, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    m = _month(month)
    n = ST.reset(db, m)
    db.commit()
    log_action(db, user, "ord_report_reset", "ord_report", None, f"Отчёт ОРД {m:%m.%Y}: правки из файла сброшены ({n})")
    return {"removed": n}


@router.post("/{month}/snapshot")
def report_snapshot(month: str, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Снять разрез по ЕРИД сейчас, не дожидаясь ночного крона."""
    from app.ord import erid_snapshot as ES
    m = _month(month)
    n = ES.capture(db, m)
    log_action(db, user, "ord_report_snapshot", "ord_report", None, f"Отчёт ОРД {m:%m.%Y}: снят разрез по ЕРИД ({n} строк)")
    return {"rows": n}
