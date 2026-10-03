# -*- coding: utf-8 -*-
"""«Импорт ADFOX» на дашборде трафика (владелец 02.10.2026): суточный отчёт Adfox → факт РК.

Два шага, как у «Обновить данные в DSP»: сначала разбор файла без записи — каждая строка
со статусом (сопоставлена / неоднозначно / не сопоставлена) и с тем, что станет с фактом
(новые данные / обновление «было → станет» / без изменений); потом запись выбранного
пачками — полоса хода на экране настоящая. Ручной выбор для неоднозначных — из
предложенных вариантов или поиском по коду.

Право — правка дашборда трафика; область видимости — та же, что у дашборда
(`traffic._apply_scope`): креатив чужой РК не находится ни сопоставлением, ни поиском, и
запись по нему отказывает.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad.models import AdCampaign
from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.routers.traffic import _apply_scope
from app.sales.models import SalesDeal
from app.traffic import adfox_import as ai

router = APIRouter()
EDIT = require_permission("traffic_dashboard", "edit")
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS_PER_CALL = 500


def _allowed(db: Session, user: User) -> set:
    """РК, которые пользователь видит на дашборде трафика."""
    q = (db.query(AdCampaign.id, SalesDeal.id)
         .join(SalesDeal, SalesDeal.id == AdCampaign.deal_id))
    return {r[0] for r in _apply_scope(q, db, user, all_reps=True).all()}


def _with_state(db: Session, rows: List[dict]) -> List[dict]:
    """Строкам с креативом — что станет с фактом их размещения за день."""
    ready = [r for r in rows if r.get("placement_id")]
    agg = ai.aggregate(ready)
    states = ai.diff(db, agg)
    for r in ready:
        k = (int(r["campaign_id"]), int(r["placement_id"]), r["day"])
        st = states.get(k) or {}
        r["change"] = st.get("state")
        r["was"] = st.get("was")
        a = agg.get(k)
        # Будущее значение — сумма по размещению за день (несколько креативов одной
        # площадки складываются), а не цифра одной строки файла.
        r["will"] = None if a is None else {"shows": a["shows"], "clicks": a["clicks"],
                                            "uniques": a["uniques"]}
    return rows


def _summary(rows: List[dict]) -> dict:
    s = {"rows": len(rows), "matched": 0, "ambiguous": 0, "unmatched": 0,
         "new": 0, "update": 0, "same": 0}
    for r in rows:
        s[r["status"]] = s.get(r["status"], 0) + 1
        if r.get("change"):
            s[r["change"]] += 1
    days = sorted({r["day"] for r in rows})
    s["days"] = [d.isoformat() for d in days]
    return s


@router.post("/preview")
async def preview(file: UploadFile = File(...), db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Разобрать отчёт и показать, что будет записано. В базу ничего не пишется."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Файл больше 5 МБ — это не суточный отчёт Adfox")
    try:
        rows = ai.parse(data)
    except ai.ImportError_ as e:
        raise HTTPException(400, str(e))
    rows = _with_state(db, ai.resolve(db, rows, _allowed(db, user)))
    return {"file": file.filename, "summary": _summary(rows), "rows": rows}


class PickRow(BaseModel):
    line: int
    day: date
    creative_id: int
    shows: int = 0
    clicks: int = 0
    uniques: Optional[int] = None


class PickIn(BaseModel):
    rows: List[PickRow]


def _bind(db: Session, user: User, rows: List[PickRow]) -> List[dict]:
    """Креатив → размещение и РК — с сервера, а не со слов экрана; чужая РК — отказ."""
    if len(rows) > MAX_ROWS_PER_CALL:
        raise HTTPException(400, f"Не больше {MAX_ROWS_PER_CALL} строк за вызов")
    ids = sorted({r.creative_id for r in rows})
    found = {r["creative_id"]: r for r in db.execute(text(
        "SELECT id AS creative_id, placement_id, campaign_id FROM ad_campaign_creative "
        "WHERE id = ANY(:i)"), {"i": ids}).mappings()}
    allowed = _allowed(db, user)
    # Размещение, которое крутится в нашей DSP, получает факт оттуда; отчёт Adfox поверх
    # задвоил бы день (ревью 03.10.2026) — такую строку не пишем.
    pls = sorted({c["placement_id"] for c in found.values() if c["placement_id"]})
    dsp_fact = {r[0] for r in db.execute(text(
        "SELECT DISTINCT placement_id FROM ad_campaign_stat WHERE placement_id = ANY(:p) "
        "AND source IN ('dsp', 'ms')"), {"p": pls})} if pls else set()
    out = []
    for r in rows:
        c = found.get(r.creative_id)
        if c is None or c["campaign_id"] not in allowed or c["placement_id"] is None:
            raise HTTPException(404, f"строка {r.line}: креатив не найден")
        if c["placement_id"] in dsp_fact:
            raise HTTPException(409, f"строка {r.line}: это размещение крутится в нашей DSP и "
                                     "уже имеет её факт — отчёт Adfox на него не пишется")
        if min(r.shows, r.clicks, r.uniques or 0) < 0:
            raise HTTPException(400, f"строка {r.line}: отрицательное число")
        out.append({**r.dict(), "placement_id": c["placement_id"], "campaign_id": c["campaign_id"]})
    return out


@router.post("/state")
def state(payload: PickIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Что станет с фактом после ручного выбора креатива — те же «новые / обновление»."""
    rows = _with_state(db, _bind(db, user, payload.rows))
    return {"rows": [{k: r.get(k) for k in ("line", "change", "was", "will")} for r in rows]}


@router.get("/search")
def search(q: str, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Поиск креатива по коду сделки, коду или домену площадки."""
    return {"items": ai.search(db, q, _allowed(db, user))}


@router.post("/apply")
def apply(payload: PickIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Записать пачку. Строки одного размещения за день приходят в одной пачке: запись
    перезаписывает сумму дня, и разрезанная пачка оставила бы в факте половину."""
    agg = ai.aggregate(_bind(db, user, payload.rows))
    n = ai.write(db, agg)
    db.commit()
    return {"written": n}


class DoneIn(BaseModel):
    file: Optional[str] = None
    written: int = 0
    skipped: int = 0
    days: List[str] = []
    error: Optional[str] = None


@router.post("/done")
def done(payload: DoneIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Одна строка журнала на загрузку, а не на пачку."""
    # Длины — от клиента, поэтому режем (ревью 03.10.2026).
    days = [str(d)[:10] for d in payload.days[:7]]
    log_action(db, user, "adfox_import", "ad_campaign", None,
               f"{(payload.file or 'отчёт Adfox')[:120]}: записано строк факта {int(payload.written)}, "
               f"пропущено строк файла {int(payload.skipped)}"
               + (f"; дни {', '.join(days)}" if days else "")
               + (f"; ПРЕРВАНО: {payload.error[:200]}" if payload.error else ""))
    return {"ok": True}
