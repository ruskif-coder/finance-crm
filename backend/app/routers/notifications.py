"""In-app уведомления: колокольчик в шапке (весь проект). Создаются при событиях
(смена статуса медиаплана и т.п.). Каждый пользователь видит только свои."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.models import User, Notification

router = APIRouter()


def create_notification(db: Session, user_id, title, kind=None, body=None, link=None,
                        entity_type=None, entity_id=None):
    """Добавить уведомление (без commit — коммитит вызывающий)."""
    if not user_id:
        return
    db.add(Notification(user_id=user_id, kind=kind, title=title, body=body, link=link,
                        entity_type=entity_type, entity_id=entity_id))


def notify_many(db: Session, user_ids, **kw):
    seen = set()
    for uid in user_ids:
        if uid and uid not in seen:
            seen.add(uid)
            create_notification(db, uid, **kw)


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = 30, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 100)).all()
    unread = db.query(Notification).filter(Notification.user_id == current_user.id,
                                           Notification.is_read.is_(False)).count()
    return {"unread": unread, "items": [{
        "id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
        "is_read": bool(n.is_read), "created_at": n.created_at,
    } for n in rows]}


@router.get("/count")
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"unread": db.query(Notification).filter(Notification.user_id == current_user.id,
                                                    Notification.is_read.is_(False)).count()}


class ReadIn(BaseModel):
    ids: Optional[List[int]] = None   # None → отметить все прочитанными


@router.post("/read")
def mark_read(data: ReadIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
    if data.ids:
        q = q.filter(Notification.id.in_(data.ids))
    q.update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
