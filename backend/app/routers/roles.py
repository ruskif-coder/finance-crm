from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.database import get_db
from app.models import User, Role, RolePermission
from app.audit import log_action, require_admin
from app.permissions import SECTIONS, ACTION_FIELDS

router = APIRouter()

# Три секции раздела «Продажи» несут ОДИН deals_scope (UI шлёт одинаковое значение
# на все три, см. settings.js SALES_KEYS). Энфорсмент own-scope читает
# sales_registry/sales_analytics, поэтому писать scope надо во все три — иначе
# «только свои» молча не срабатывает (роль продолжает видеть все сделки).
_SALES_SECTIONS = ("sales_dashboard", "sales_registry", "sales_analytics")
# Медиапланы несут собственный (независимый от продаж) deals_scope: реестр и
# конструктор делят одно значение, UI шлёт его в обе секции (см. settings/roles.js).
_MP_SECTIONS = ("media_plans", "media_plans_editor")
_SCOPED_SECTIONS = _SALES_SECTIONS + _MP_SECTIONS


class PermissionInput(BaseModel):
    section: str
    can_view: Optional[bool] = None
    can_create: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_view_operations: Optional[bool] = None
    deals_scope: Optional[str] = None   # all | own — для секции sales_dashboard


class RoleCreate(BaseModel):
    label: str


class RoleUpdate(BaseModel):
    label: Optional[str] = None
    permissions: Optional[List[PermissionInput]] = None
    staff_group: Optional[str] = None   # 'seller' / 'account' / 'traffic' / '' (снять)
    is_master: Optional[bool] = None


def _serialize_role(db: Session, role: Role) -> dict:
    rows = {r.section: r for r in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()}
    permissions = {}
    for s in SECTIONS:
        if role.key == "admin":
            permissions[s["key"]] = {a: True for a in s["actions"]}
            continue
        row = rows.get(s["key"])
        permissions[s["key"]] = {
            a: bool(getattr(row, ACTION_FIELDS[a])) if row else False
            for a in s["actions"]
        }
    user_count = db.query(User).filter(User.role_id == role.id).count()
    sd = rows.get("sales_dashboard")
    mp = rows.get("media_plans")
    deals_scope = "all" if role.key == "admin" else ((sd.deals_scope if sd else None) or "all")
    mp_scope = "all" if role.key == "admin" else ((mp.deals_scope if mp else None) or "all")
    return {
        "id": role.id,
        "key": role.key,
        "label": role.label,
        "is_system": bool(role.is_system),
        "user_count": user_count,
        "permissions": permissions,
        "deals_scope": deals_scope,
        "mp_scope": mp_scope,
        "staff_group": role.staff_group or "",
        "is_master": bool(role.is_master),
    }


@router.get("/")
def list_roles(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    roles = db.query(Role).order_by(Role.id).all()
    return {
        "roles": [_serialize_role(db, r) for r in roles],
        "sections": SECTIONS,
    }


@router.post("/")
def create_role(data: RoleCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    label = (data.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Укажите название роли")

    role = Role(key="", label=label, is_system=0)
    db.add(role)
    db.commit()
    db.refresh(role)
    role.key = f"role_{role.id}"
    for s in SECTIONS:
        db.add(RolePermission(role_id=role.id, section=s["key"]))
    db.commit()

    log_action(db, current_user, "create_role", entity_type="role", entity_id=role.id,
               details=f"Создана роль «{role.label}»")
    return {"id": role.id, "message": "Роль создана"}


@router.put("/{role_id}")
def update_role(role_id: int, data: RoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    if role.key == "admin":
        raise HTTPException(status_code=400, detail="Нельзя изменить роль администратора")

    changes = []
    if data.label is not None and data.label.strip() and data.label.strip() != role.label:
        changes.append(f"название: {role.label} → {data.label.strip()}")
        role.label = data.label.strip()

    # Рабочая группа + мастер (классификация роли для конструктора МП).
    if data.staff_group is not None:
        role.staff_group = data.staff_group if data.staff_group in ("seller", "account", "traffic") else None
        changes.append(f"рабочая группа: {role.staff_group or '—'}")
    if data.is_master is not None:
        role.is_master = bool(data.is_master)
        changes.append(f"мастер: {'да' if role.is_master else 'нет'}")

    if data.permissions:
        valid_sections = {s["key"]: s["actions"] for s in SECTIONS}
        for p in data.permissions:
            if p.section not in valid_sections:
                continue
            row = db.query(RolePermission).filter(
                RolePermission.role_id == role.id, RolePermission.section == p.section
            ).first()
            if not row:
                row = RolePermission(role_id=role.id, section=p.section)
                db.add(row)
            for action in valid_sections[p.section]:
                val = getattr(p, ACTION_FIELDS[action])
                if val is not None:
                    setattr(row, ACTION_FIELDS[action], 1 if val else 0)
            # Видимость (own/all) — секции продаж (общий scope) и медиапланов (свой).
            if p.section in _SCOPED_SECTIONS and p.deals_scope is not None:
                row.deals_scope = p.deals_scope if p.deals_scope in ("all", "own") else "all"
        changes.append("права доступа изменены")

    db.commit()
    if changes:
        log_action(db, current_user, "update_role", entity_type="role", entity_id=role.id,
                   details=f"{role.label}: " + "; ".join(changes))
    return {"message": "Роль обновлена"}


@router.delete("/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Нельзя удалить системную роль")
    in_use = db.query(User).filter(User.role_id == role.id).count()
    if in_use:
        raise HTTPException(status_code=400, detail=f"Роль используется у {in_use} пользователей — сначала смените им роль")

    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    label = role.label
    db.delete(role)
    db.commit()

    log_action(db, current_user, "delete_role", entity_type="role", entity_id=role_id,
               details=f"Удалена роль «{label}»")
    return {"message": "Роль удалена"}
