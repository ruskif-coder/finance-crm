from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RolePermission
from app.routers.auth import get_current_user

# Канонический список разделов, доступных настройке через менеджер ролей.
# "Пользователи" и "Журнал действий" сюда не входят — они жёстко закрыты под admin (см. app.audit.require_admin).
SECTIONS = [
    {"key": "dashboard",         "label": "ДДС",                "group": "Отчёты",    "actions": ["view"]},
    {"key": "pl",                "label": "P&L",                "group": "Отчёты",    "actions": ["view"]},
    {"key": "balance",           "label": "Баланс",             "group": "Отчёты",    "actions": ["view"]},
    {"key": "planfact",          "label": "План / Факт",        "group": "Отчёты",    "actions": ["view"]},
    {"key": "receivables",       "label": "Дебиторская задолженность", "group": "Отчёты", "actions": ["view", "edit"]},
    {"key": "operations",        "label": "Операции",           "group": None,        "actions": ["view", "create", "edit", "delete"]},
    {"key": "import",            "label": "Импорт",             "group": None,        "actions": ["view"]},
    {"key": "settings_balances", "label": "Остатки по банкам",  "group": "Настройки", "actions": ["view", "edit"]},
    {"key": "counterparties",    "label": "Контрагенты",        "group": "Справочники", "actions": ["view", "edit", "delete"]},
    {"key": "articles",          "label": "Статьи",             "group": "Справочники", "actions": ["view", "edit"]},
    {"key": "contracts",         "label": "Договоры",           "group": "Справочники", "actions": ["view", "edit"]},
]

ACTION_FIELDS = {"view": "can_view", "create": "can_create", "edit": "can_edit", "delete": "can_delete"}


def get_permissions_for_user(db: Session, user: User) -> dict:
    """Возвращает {section: {action: bool}} для пользователя. Admin всегда получает полный доступ
    (без хранения строк в role_permissions — это и есть смысл «бессмертной» системной роли)."""
    if user.role.key == "admin":
        return {s["key"]: {a: True for a in s["actions"]} for s in SECTIONS}

    rows = db.query(RolePermission).filter(RolePermission.role_id == user.role_id).all()
    by_section = {r.section: r for r in rows}

    result = {}
    for s in SECTIONS:
        row = by_section.get(s["key"])
        result[s["key"]] = {
            a: bool(getattr(row, ACTION_FIELDS[a])) if row else False
            for a in s["actions"]
        }
    return result


def require_permission(section: str, action: str = "view"):
    """Фабрика зависимостей FastAPI: пропускает запрос, только если у роли пользователя есть
    разрешение can_<action> для данного раздела. Admin всегда проходит без проверки."""
    def checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if current_user.role.key == "admin":
            return current_user
        row = db.query(RolePermission).filter(
            RolePermission.role_id == current_user.role_id,
            RolePermission.section == section,
        ).first()
        field = ACTION_FIELDS.get(action, "can_view")
        allowed = bool(getattr(row, field)) if row else False
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия")
        return current_user
    return checker
