from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.database import get_db
from app.models import User, Role, RolePermission
from app.audit import log_action, require_admin
from app.permissions import SECTIONS, ACTION_FIELDS

router = APIRouter()


class PermissionInput(BaseModel):
    section: str
    can_view: Optional[bool] = None
    can_create: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_view_operations: Optional[bool] = None


class RoleCreate(BaseModel):
    label: str


class RoleUpdate(BaseModel):
    label: Optional[str] = None
    permissions: Optional[List[PermissionInput]] = None


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
    return {
        "id": role.id,
        "key": role.key,
        "label": role.label,
        "is_system": bool(role.is_system),
        "user_count": user_count,
        "permissions": permissions,
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
