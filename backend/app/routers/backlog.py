"""Бэклог отладки — что держим под наблюдением после больших изменений.

Журнал действий отвечает на вопрос «что было сделано», этот раздел — «что может
выстрелить и по какому признаку это опознать». Отсюда обязательность `resolution`
при закрытии: запись, закрытая без объяснения, не отличается от забытой.

Схема: backend/migrations/2026-08-16_debug_backlog.sql
Модели: app/backlog_models.py
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.audit import log_action
from app.backlog_models import (CLOSED_STATUSES, SEVERITIES, STATUSES,
                                BacklogItem, BacklogNote)
from app.database import get_db
from app.models import User
from app.notify import emit
from app.permissions import require_permission

router = APIRouter()

# Порядок важности для сортировки: чем больше вес, тем выше в списке.
SEVERITY_WEIGHT = {"высокая": 0, "средняя": 1, "низкая": 2}

# Статус «подтвердилось» — не закрытие (наблюдение продолжается), но опасение сбылось,
# поэтому дата/автор проставляются так же, как при закрытии: это фиксация исхода.
RESOLVING_STATUSES = set(CLOSED_STATUSES) | {"подтвердилось"}


# ─────────────────────────── схемы ───────────────────────────

class BacklogIn(BaseModel):
    title: str
    area: Optional[str] = None
    context: Optional[str] = None
    signal_ok: Optional[str] = None
    signal_bad: Optional[str] = None
    severity: str = "средняя"
    status: str = "наблюдаем"
    watch_until: Optional[date] = None
    source_link: Optional[str] = None
    resolution: Optional[str] = None


class BacklogUpdate(BaseModel):
    """Частичное обновление тем же паттерном, что bulk-edit в operations.py:
    все поля Optional, реально пишутся только те, что пришли (exclude_unset)."""
    title: Optional[str] = None
    area: Optional[str] = None
    context: Optional[str] = None
    signal_ok: Optional[str] = None
    signal_bad: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    watch_until: Optional[date] = None
    source_link: Optional[str] = None
    resolution: Optional[str] = None


class NoteIn(BaseModel):
    text: str


# ─────────────────────────── помощники ───────────────────────────

def _validate(severity: Optional[str], status: Optional[str]):
    if severity is not None and severity not in SEVERITIES:
        raise HTTPException(400, f"Недопустимая важность: {severity}. "
                                 f"Допустимо: {', '.join(SEVERITIES)}")
    if status is not None and status not in STATUSES:
        raise HTTPException(400, f"Недопустимый статус: {status}. "
                                 f"Допустимо: {', '.join(STATUSES)}")


def apply_status_change(item: BacklogItem, new_status: str, user: User,
                        now: Optional[datetime] = None):
    """Единственное место, где живёт связка статус ↔ resolved_at/resolved_by.

    Закрытие без `resolution` запрещено: смысл записи в том, чем всё кончилось,
    без этого текста список через месяц превращается в свалку.
    """
    now = now or datetime.utcnow()
    if new_status in RESOLVING_STATUSES:
        if new_status in CLOSED_STATUSES and not (item.resolution or "").strip():
            raise HTTPException(
                400, "Нельзя закрыть запись без описания результата: "
                     "заполните поле «Чем кончилось»")
        item.resolved_at = now
        item.resolved_by = getattr(user, "id", None)
    else:
        # Вернули под наблюдение — прежний исход больше не действителен,
        # иначе запись выглядит закрытой и одновременно открытой.
        item.resolved_at = None
        item.resolved_by = None
        item.overdue_notified_at = None
    item.status = new_status


def is_overdue(item: BacklogItem, today: Optional[date] = None) -> bool:
    today = today or date.today()
    return bool(item.watch_until and item.status not in CLOSED_STATUSES
                and item.watch_until < today)


def _sort_key(row: dict):
    closed = 1 if row["status"] in CLOSED_STATUSES else 0
    overdue = 0 if row["overdue"] else 1
    sev = SEVERITY_WEIGHT.get(row["severity"], 9)
    created = row["created_at"] or datetime.min
    # Секунды от datetime.min, а НЕ `.timestamp()`. У наивной даты `.timestamp()`
    # читает её как МЕСТНОЕ время процесса, и с 23.09.2026, когда процесс перешёл на
    # Москву, `datetime.min.timestamp()` падает: «year 0 is out of range» (сдвиг на три
    # часа уводит нулевой год за границу календаря). Одна запись без `created_at` роняла
    # бы весь экран «Бэклог отладки». Разность двух наивных дат пояса не знает вовсе.
    return (closed, overdue, sev, -(created - datetime.min).total_seconds())


def _serialize(item: BacklogItem, notes_count: int, created_name: Optional[str],
               resolved_name: Optional[str], today: date) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "area": item.area,
        "context": item.context,
        "signal_ok": item.signal_ok,
        "signal_bad": item.signal_bad,
        "severity": item.severity,
        "status": item.status,
        "watch_until": item.watch_until,
        "source_link": item.source_link,
        "created_at": item.created_at,
        "created_by": item.created_by,
        "created_by_name": created_name,
        "resolved_at": item.resolved_at,
        "resolved_by": item.resolved_by,
        "resolved_by_name": resolved_name,
        "resolution": item.resolution,
        "notes_count": notes_count,
        "overdue": is_overdue(item, today),
    }


# ─────────────────────────── эндпоинты ───────────────────────────

@router.get("/areas")
def list_areas(db: Session = Depends(get_db),
               current_user: User = Depends(require_permission("settings_backlog", "view"))):
    """Уникальные разделы — для выпадашки фильтра. Отдельным эндпоинтом, чтобы
    список не зависел от фильтров и пагинации самого реестра."""
    rows = (db.query(BacklogItem.area)
            .filter(BacklogItem.area.isnot(None), BacklogItem.area != "")
            .distinct().order_by(BacklogItem.area).all())
    return [r[0] for r in rows]


@router.get("")
@router.get("/")
def list_items(status: Optional[str] = None, area: Optional[str] = None,
               severity: Optional[str] = None, q: Optional[str] = None,
               overdue: bool = Query(False),
               db: Session = Depends(get_db),
               current_user: User = Depends(require_permission("settings_backlog", "view"))):
    """Реестр записей.

    Имена людей и число наблюдений добираются джойнами в этом же запросе:
    список открывают целиком, и N+1 на каждую строку здесь особенно заметен.
    """
    creator = aliased(User)
    resolver = aliased(User)
    notes_cnt = (db.query(BacklogNote.item_id.label("item_id"),
                          func.count(BacklogNote.id).label("cnt"))
                 .group_by(BacklogNote.item_id).subquery())

    query = (db.query(BacklogItem, creator.name, resolver.name,
                      func.coalesce(notes_cnt.c.cnt, 0))
             .outerjoin(creator, creator.id == BacklogItem.created_by)
             .outerjoin(resolver, resolver.id == BacklogItem.resolved_by)
             .outerjoin(notes_cnt, notes_cnt.c.item_id == BacklogItem.id))

    if status:
        query = query.filter(BacklogItem.status == status)
    if area:
        query = query.filter(BacklogItem.area == area)
    if severity:
        query = query.filter(BacklogItem.severity == severity)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(BacklogItem.title.ilike(like),
                                 BacklogItem.context.ilike(like)))
    today = date.today()
    if overdue:
        query = query.filter(BacklogItem.watch_until.isnot(None),
                             BacklogItem.watch_until < today,
                             BacklogItem.status.notin_(list(CLOSED_STATUSES)))

    rows = [_serialize(it, cnt, cname, rname, today)
            for it, cname, rname, cnt in query.all()]
    rows.sort(key=_sort_key)
    return rows


@router.get("/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(require_permission("settings_backlog", "view"))):
    creator = aliased(User)
    resolver = aliased(User)
    row = (db.query(BacklogItem, creator.name, resolver.name)
           .outerjoin(creator, creator.id == BacklogItem.created_by)
           .outerjoin(resolver, resolver.id == BacklogItem.resolved_by)
           .filter(BacklogItem.id == item_id).first())
    if not row:
        raise HTTPException(404, "Запись не найдена")
    item, cname, rname = row

    authors = {u.id: u.name for u in db.query(User).filter(
        User.id.in_([n.author_id for n in item.notes if n.author_id] or [0])).all()}
    data = _serialize(item, len(item.notes), cname, rname, date.today())
    data["notes"] = [{"id": n.id, "text": n.text, "created_at": n.created_at,
                      "author_id": n.author_id, "author_name": authors.get(n.author_id)}
                     for n in item.notes]
    return data


@router.post("")
@router.post("/")
def create_item(payload: BacklogIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_permission("settings_backlog", "create"))):
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(400, "Название записи обязательно")
    _validate(payload.severity, payload.status)

    item = BacklogItem(**{**payload.dict(), "title": title})
    item.created_by = current_user.id
    item.created_at = datetime.utcnow()
    if payload.status != "наблюдаем":
        apply_status_change(item, payload.status, current_user)
    db.add(item)
    db.commit()
    db.refresh(item)

    log_action(db, current_user, "backlog_create", "backlog", item.id,
               f"Заведена запись наблюдения: {item.title}")
    emit(db, "backlog_created", title=f"Новое наблюдение: {item.title}",
         body=item.context, link="/settings/backlog",
         entity_type="backlog", entity_id=item.id, actor=current_user)
    db.commit()
    return _serialize(item, 0, current_user.name, None, date.today())


@router.put("/{item_id}")
def update_item(item_id: int, payload: BacklogUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(require_permission("settings_backlog", "edit"))):
    item = db.query(BacklogItem).filter(BacklogItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Запись не найдена")

    data = payload.dict(exclude_unset=True)
    _validate(data.get("severity"), data.get("status"))
    if "title" in data:
        if not (data["title"] or "").strip():
            raise HTTPException(400, "Название записи обязательно")
        data["title"] = data["title"].strip()

    new_status = data.pop("status", None)
    old_status = item.status
    for field, value in data.items():
        setattr(item, field, value)
    # Статус применяется ПОСЛЕ остальных полей: проверка «закрыто без resolution»
    # должна видеть текст, присланный этим же запросом.
    if new_status is not None and new_status != old_status:
        apply_status_change(item, new_status, current_user)
    db.commit()
    db.refresh(item)

    changed = ", ".join(sorted(data.keys())) or "—"
    if new_status is not None and new_status != old_status:
        log_action(db, current_user, "backlog_status", "backlog", item.id,
                   f"Статус: {old_status} → {new_status} ({item.title})")
        if new_status == "подтвердилось":
            emit(db, "backlog_confirmed",
                 title=f"Опасение подтвердилось: {item.title}",
                 body=item.signal_bad or item.context, link="/settings/backlog",
                 entity_type="backlog", entity_id=item.id, actor=current_user)
    else:
        log_action(db, current_user, "backlog_update", "backlog", item.id,
                   f"Правка записи «{item.title}»: {changed}")
    db.commit()

    creator = db.query(User).filter(User.id == item.created_by).first()
    resolver = db.query(User).filter(User.id == item.resolved_by).first()
    return _serialize(item, len(item.notes),
                      creator.name if creator else None,
                      resolver.name if resolver else None, date.today())


@router.post("/{item_id}/notes")
def add_note(item_id: int, payload: NoteIn, db: Session = Depends(get_db),
             current_user: User = Depends(require_permission("settings_backlog", "edit"))):
    item = db.query(BacklogItem).filter(BacklogItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Запись не найдена")
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Текст наблюдения обязателен")

    note = BacklogNote(item_id=item.id, author_id=current_user.id, text=text,
                       created_at=datetime.utcnow())
    db.add(note)
    db.commit()
    db.refresh(note)
    log_action(db, current_user, "backlog_note", "backlog", item.id,
               f"Наблюдение по записи «{item.title}»")
    return {"id": note.id, "text": note.text, "created_at": note.created_at,
            "author_id": note.author_id, "author_name": current_user.name}
