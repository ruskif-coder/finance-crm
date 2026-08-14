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


# ── Вид события → тон, вкладка виджета и подпись кнопки ──────────────────
# Единственная точка правды для оформления уведомления. Новый тип события =
# одна строка здесь; в интерфейсе ничего не хардкодим.
#   tone:  danger | warning | success | info
#   group: Сделки | Документы | Оплаты | Брифы (вкладки виджета на дашборде)
KIND_META = {
    "mp_submit":   {"tone": "info", "group": "Документы", "action": "Открыть МП"},
    "mp_approved": {"tone": "success", "group": "Документы", "action": ""},
    "mp_rejected": {"tone": "danger", "group": "Документы", "action": "Открыть МП"},
    "mp_archived": {"tone": "info", "group": "Документы", "action": ""},
    "mp_recalled": {"tone": "warning", "group": "Документы", "action": "Открыть МП"},
    # легаси: до разделения на конкретные виды все статусы МП писались одним kind
    "mp_status":   {"tone": "info", "group": "Документы", "action": "Открыть МП"},
    "deal_stage":  {"tone": "success", "group": "Сделки", "action": "Открыть сделку"},
    "deal_brief":  {"tone": "info", "group": "Брифы", "action": "Открыть сделку"},
    "payment":     {"tone": "success", "group": "Оплаты", "action": ""},
}
DEFAULT_META = {"tone": "info", "group": "Сделки", "action": ""}


def _where_map(db, rows):
    """«Где» для строки уведомления — «Рекламодатель · Бренд» объекта события.
    Считаем пачкой по entity_type, чтобы не ловить N+1 на списке."""
    from app.sales.models import SalesDeal, SalesMediaPlan, SalesAdvertiser, SalesBrand
    ids = {"media_plan": set(), "sales_deal": set()}
    for n in rows:
        if n.entity_type in ids and n.entity_id:
            ids[n.entity_type].add(n.entity_id)
    if not any(ids.values()):
        return {}
    adv = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.short_name).all())
    adv_full = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.name).all())
    brands = dict(db.query(SalesBrand.id, SalesBrand.name).all())

    def label(advertiser_id, brand_id):
        a = adv.get(advertiser_id) or adv_full.get(advertiser_id)
        b = brands.get(brand_id)
        return " · ".join([x for x in (a, b) if x])

    out = {}
    if ids["media_plan"]:
        for p in db.query(SalesMediaPlan).filter(SalesMediaPlan.id.in_(ids["media_plan"])).all():
            out[("media_plan", p.id)] = label(p.advertiser_id, p.brand_id)
    if ids["sales_deal"]:
        for d in db.query(SalesDeal).filter(SalesDeal.id.in_(ids["sales_deal"])).all():
            out[("sales_deal", d.id)] = label(d.advertiser_id, d.brand_id)
    return out


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = 30, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 100)).all()
    unread = db.query(Notification).filter(Notification.user_id == current_user.id,
                                           Notification.is_read.is_(False)).count()
    where = _where_map(db, rows)

    def item(n):
        m = KIND_META.get(n.kind or "", DEFAULT_META)
        return {
            "id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "is_read": bool(n.is_read), "created_at": n.created_at,
            # поля для виджета уведомлений на дашборде
            "tone": m["tone"], "group": m["group"],
            "action": m["action"] if n.link else "",
            "where": where.get((n.entity_type, n.entity_id)) or "",
        }

    return {"unread": unread, "items": [item(n) for n in rows]}


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
