from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Role, AuditLog
from app.audit import log_action, require_admin
from app.routers.auth import get_password_hash
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta

router = APIRouter()


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("/")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    users = db.query(User).order_by(User.created_at).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role.key,
            "role_label": u.role.label,
            "is_active": bool(u.is_active),
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.post("/")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
    role = db.query(Role).filter(Role.key == data.role).first()
    if not role:
        raise HTTPException(status_code=400, detail="Недопустимая роль")

    user = User(
        name=data.name,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, current_user, "create_user", entity_type="user", entity_id=user.id,
               details=f"Создан пользователь {user.name} ({user.email}), роль {role.label}")
    return {"id": user.id, "message": "Пользователь создан"}


@router.put("/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    changes = []

    if data.name is not None and data.name != user.name:
        changes.append(f"имя: {user.name} → {data.name}")
        user.name = data.name

    if data.role is not None and data.role != user.role.key:
        new_role = db.query(Role).filter(Role.key == data.role).first()
        if not new_role:
            raise HTTPException(status_code=400, detail="Недопустимая роль")
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Нельзя изменить собственную роль")
        changes.append(f"роль: {user.role.label} → {new_role.label}")
        user.role_id = new_role.id

    if data.is_active is not None and bool(user.is_active) != data.is_active:
        if user.id == current_user.id and not data.is_active:
            raise HTTPException(status_code=400, detail="Нельзя деактивировать самого себя")
        changes.append("активирован" if data.is_active else "деактивирован")
        user.is_active = 1 if data.is_active else 0

    if data.password:
        if len(data.password) < 8:
            raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
        changes.append("пароль изменён")
        user.hashed_password = get_password_hash(data.password)

    db.commit()

    if changes:
        log_action(db, current_user, "update_user", entity_type="user", entity_id=user.id,
                   details=f"{user.name} ({user.email}): " + "; ".join(changes))

    return {"message": "Пользователь обновлён"}


ACTION_LABELS = {
    "login_success": "Вход выполнен",
    "login_failed": "Неудачный вход",
    "create_user": "Создание пользователя",
    "update_user": "Изменение пользователя",
    "create_operation": "Создание операции",
    "update_operation": "Изменение операции",
    "delete_operation": "Удаление операции",
    "create_role": "Создание роли",
    "update_role": "Изменение роли",
    "delete_role": "Удаление роли",
    "update_counterparty": "Изменение контрагента",
    "delete_counterparty": "Удаление контрагента",
    "bulk_update_counterparty": "Массовое изменение контрагентов",
}


@router.get("/audit-log/")
def get_audit_log(
    skip: int = 0,
    limit: int = 100,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at < date_to + timedelta(days=1))

    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "actions": ACTION_LABELS,
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_name": r.user_name,
                "action": r.action,
                "action_label": ACTION_LABELS.get(r.action, r.action),
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "details": r.details,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }
