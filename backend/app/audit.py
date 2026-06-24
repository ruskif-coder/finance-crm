from sqlalchemy.orm import Session
from app.models import AuditLog, User
from fastapi import Depends, HTTPException, status
from app.routers.auth import get_current_user


def log_action(db: Session, user: User | None, action: str, entity_type: str = None, entity_id: int = None, details: str = None):
    """Записывает действие в журнал. user может быть None (например, неуспешный вход с неизвестным email)."""
    entry = AuditLog(
        user_id=user.id if user else None,
        user_name=user.name if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    db.commit()


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Зависимость FastAPI: пропускает только пользователей с ролью admin."""
    if current_user.role.key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступно только администратору")
    return current_user
