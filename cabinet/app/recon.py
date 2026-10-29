"""Сверка месяца в кабинете площадки (26.10.2026; хендофф docs/карточка сверки.zip, план docs/ПЛАН_сверка_паблишера.md).

Читаем — `pub.recon_v1`, `pub.recon_message_v1`, `pub.recon_file_v1` и кампании месяца из `pub.campaign_v1` (то же число,
что видит менеджер: одно представление факта). Пишем — через ядро (`/api/cabinet-gw/recon/*`), как вердикты креатива.
Подключается в конце `app/main.py`, поэтому берёт оттуда общие двери ядра.
"""
from datetime import date
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import account_publishers, current_account
from app.db import scoped_session
from app.main import ATTACH_MAX, CORE_API_URL, SERVICE_TOKEN, _to_msk, call_core, read_capped, require_approver

router = APIRouter()
AGREED = "согласовано"


def _iso(v):
    return v.isoformat() if v is not None else None



def _mine(acc, request_id: int):
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        raise HTTPException(status_code=404, detail="Сверка не найдена")
    with scoped_session(ids) as db:
        row = db.execute(text("SELECT request_id, publisher_id, verdict FROM pub.recon_v1 WHERE request_id = :r"),
                         {"r": request_id}).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Сверка не найдена")
    return row


@router.get("/api/recons")
def recons(acc=Depends(current_account)):
    """Открытые сверки площадок учётки: карточка очереди, модалка с кампаниями и переписка.
    Согласованная сверка из очереди уходит (её итог зафиксирован без возврата)."""
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        return {"items": []}
    with scoped_session(ids) as db:
        reqs = db.execute(text("SELECT * FROM pub.recon_v1 WHERE verdict IS NULL ORDER BY due_at, request_id")).mappings().all()
        if not reqs:
            return {"items": []}
        rids = [r["request_id"] for r in reqs]
        msgs = db.execute(text("SELECT * FROM pub.recon_message_v1 WHERE request_id = ANY(:r) ORDER BY message_id"),
                          {"r": rids}).mappings().all()
        files = db.execute(text("SELECT * FROM pub.recon_file_v1 WHERE request_id = ANY(:r) ORDER BY file_id"),
                           {"r": rids}).mappings().all()
        camps = db.execute(text("""
            SELECT publisher_id, to_char(date_from, 'YYYY-MM') AS period, brand, service, surface, date_from, date_to,
                   erid, plan, fact, cpm, status
              FROM pub.campaign_v1 WHERE status <> 'отказ' OR fact > 0 ORDER BY fact DESC""")).mappings().all()
    files_of = {}
    for f in files:
        files_of.setdefault(f["message_id"], []).append({"id": f["file_id"], "name": f["name"], "size_bytes": f["size_bytes"]})
    msgs_of = {}
    for m in msgs:
        msgs_of.setdefault(m["request_id"], []).append({
            "id": m["message_id"], "side": m["side"], "author_name": m["author_name"], "body": m["body"],
            "volume": m["shows"], "created_at": _iso(_to_msk(m["created_at"])), "files": files_of.get(m["message_id"], [])})
    out = []
    for r in reqs:
        cs = [c for c in camps if c["publisher_id"] == r["publisher_id"] and c["period"] == r["period"]]
        out.append({
            "id": r["request_id"], "publisher_id": r["publisher_id"], "site": r["site"], "period": r["period"],
            "asked_at": _iso(r["asked_at"]), "due_at": _iso(r["due_at"]), "last_side": r["last_side"],
            # Просрочено — тем же правилом, что у менеджера (`publisher_recon.board.status_of`): срок раньше сегодня.
            # Срок уже в рабочих днях; второй подсчёт в браузере расходился с доской в выходные (ревью 26.10.2026).
            "late": bool(r["due_at"] and r["due_at"] < date.today()),
            "offer": r["offer"], "unread": int(r["unread"] or 0), "messages": int(r["messages"] or 0),
            # Наш факт — живой, по кампаниям месяца (то же правило, что у менеджера): снимок при отправке отстаёт
            # от досчёта DSP, и площадка видела бы в карточке одну цифру, а в таблице под ней — другую.
            "our_volume": sum(int(c["fact"] or 0) for c in cs), "their_volume": r["their_volume"],
            "cpm": float(r["cpm"]) if r["cpm"] is not None else None,
            "campaigns": [{"brand": c["brand"], "service": c["service"], "surface": c["surface"],
                           "date_from": _iso(c["date_from"]), "date_to": _iso(c["date_to"]), "erid": c["erid"],
                           "plan": int(c["plan"] or 0), "fact": int(c["fact"] or 0)} for c in cs],
            "thread": msgs_of.get(r["request_id"], []),
        })
    return {"items": out}


class AnswerIn(BaseModel):
    kind: str                       # согласен | расхождение | сообщение
    volume: Optional[int] = None
    body: Optional[str] = None


@router.post("/api/recons/{request_id}/answer")
def answer(request_id: int, payload: AnswerIn, acc=Depends(current_account)):
    if payload.kind not in ("согласен", "расхождение", "сообщение"):
        raise HTTPException(status_code=400, detail="Неизвестный ответ")
    row = _mine(acc, request_id)
    require_approver(acc)
    return call_core("POST", f"/api/cabinet-gw/recon/{request_id}/answer", {
        "publisher_id": row.publisher_id, "account_id": acc.id, "kind": payload.kind,
        "volume": payload.volume, "body": payload.body, "author_name": acc.name, "author_email": acc.email})


@router.post("/api/recons/{request_id}/seen")
def seen(request_id: int, acc=Depends(current_account)):
    """Переписку открыли — счётчик нового ответа на карточке гаснет."""
    row = _mine(acc, request_id)
    return call_core("POST", f"/api/cabinet-gw/recon/{request_id}/seen",
                     {"publisher_id": row.publisher_id, "account_id": acc.id})


def _core_or_503():
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="Кабинет не настроен на связь с системой")


@router.post("/api/recons/{request_id}/file")
async def upload(request_id: int, message_id: int, file: UploadFile = File(...), acc=Depends(current_account)):
    """Файл статистики площадки — к её сообщению этой сверки. Файл пишет ядро — том смонтирован только туда."""
    row = _mine(acc, request_id)
    require_approver(acc)
    _core_or_503()
    data = await read_capped(file, ATTACH_MAX)
    try:
        r = httpx.post(f"{CORE_API_URL}/api/cabinet-gw/recon/{request_id}/file",
                       params={"publisher_id": row.publisher_id, "account_id": acc.id, "message_id": message_id},
                       files={"file": (file.filename, data, file.content_type or "application/octet-stream")},
                       headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=60.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or "Не удалось приложить файл"
        except Exception:      # noqa: BLE001 — ядро могло ответить не JSON
            detail = "Не удалось приложить файл"
        raise HTTPException(status_code=r.status_code if r.status_code < 500 else 502, detail=detail)
    return r.json()


def _core_file(path: str, params: dict):
    """Файл сверки из ядра — учётка и площадка ИЗ сверки, а не из запроса. Ответ ядра как есть — код разбирает вызывающий."""
    _core_or_503()
    try:
        r = httpx.get(f"{CORE_API_URL}/api/cabinet-gw/recon/{path}", params=params,
                      headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=120.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Система временно недоступна — попробуйте позже")
    return r


def _as_file(r, media: str) -> Response:
    return Response(content=r.content, media_type=media,
                    headers={"Content-Disposition": r.headers.get("content-disposition", "attachment")})


@router.get("/api/recons/{request_id}/files/{file_id}")
def download(request_id: int, file_id: int, acc=Depends(current_account)):
    row = _mine(acc, request_id)
    r = _core_file(f"{request_id}/file/{file_id}", {"account_id": acc.id, "publisher_id": row.publisher_id})
    if r.status_code >= 400:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return _as_file(r, "application/octet-stream")


# ── Разаллокация (владелец 29.10.2026): после согласованной сверки мы раскладываем итог по изначальным договорам ОРД,
# площадка сдаёт по ней свой акт. Список — для ссылок на экране «Кампании», файл собирает ядро.

@router.get("/api/recons/agreed")
def agreed(acc=Depends(current_account)):
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        return {"items": []}
    with scoped_session(ids) as db:
        rows = db.execute(text("SELECT request_id, publisher_id, site, period FROM pub.recon_v1 WHERE verdict = :v "
                               "ORDER BY period DESC, site"), {"v": AGREED}).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.get("/api/recons/razaloc")
def razaloc(ids: List[int] = Query(...), acc=Depends(current_account)):
    """Кнопка в шапке месяца: все согласованные сверки месяца одним файлом, площадка — на своей вкладке (владелец 29.10.2026)."""
    if not 0 < len(ids) <= 100:
        raise HTTPException(status_code=400, detail="Нужен список сверок, не больше 100")
    if any(_mine(acc, rid).verdict != AGREED for rid in ids):
        raise HTTPException(status_code=409, detail="Разаллокация появится после согласования сверки")
    r = _core_file("razaloc.xlsx", {"account_id": acc.id, "ids": list(ids)})
    if r.status_code >= 400:
        raise HTTPException(status_code=404 if r.status_code == 404 else 502, detail="Не удалось собрать разаллокацию")
    return _as_file(r, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
