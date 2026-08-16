from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RolePermission
from app.routers.auth import get_current_user

# Канонический список разделов, доступных настройке через менеджер ролей.
# "Пользователи" и "Роли" сюда не входят — они жёстко закрыты под admin (privilege
# escalation: правка ролей = выдать себе что угодно; правка юзеров = сброс паролей).
# Раздел настраивается матрицей ролей: разделы по вертикали, роли по горизонтали
# (settings.js). Группы (group) идут по соседству — их заголовки рисуются один раз.
# Секции «Продажи» и «Справочники продаж» покрывают вложенные подстраницы:
#   sales_dashboard   → Дашборд · Реестр сделок · Аналитика (общий data-слой, одно право);
#   sales_directories → Рекламодатели · Агентства · Воронки · Услуги · Бренды · Прайс.
# Отдельных прав на каждую подстраницу не заводим: они делят одни и те же эндпойнты,
# гейтить их порознь сейчас было бы косметикой. При необходимости — расщепить позже.
SECTIONS = [
    {"key": "dashboard",         "label": "ДДС",                "group": "Финансы",    "actions": ["view"]},
    {"key": "pl",                "label": "P&L",                "group": "Финансы",    "actions": ["view"]},
    {"key": "balance",           "label": "Баланс",             "group": "Финансы",    "actions": ["view"]},
    {"key": "planfact",          "label": "План / Факт",        "group": "Финансы",    "actions": ["view"]},
    {"key": "receivables",       "label": "Дебиторская задолженность", "group": "Финансы", "actions": ["view", "edit"]},
    # Раздел «Продажи» — три отдельные страницы. Действие "edit" на реестре гейтит
    # правку сделок и синхронизацию. deals_scope (all/own) — видимость сделок,
    # задаётся 5-уровневым контролом матрицы (нет/просмотр-свои/все/ред.-свои/все).
    {"key": "sales_dashboard",   "label": "Продажи · Дашборд",       "group": "Продажи", "actions": ["view", "edit"]},
    {"key": "sales_registry",    "label": "Продажи · Реестр сделок",  "group": "Продажи", "actions": ["view", "edit"]},
    {"key": "sales_analytics",   "label": "Продажи · Аналитика",      "group": "Продажи", "actions": ["view", "edit"]},
    {"key": "year_plan",         "label": "Продажи · Годовой план",   "group": "Продажи", "actions": ["view", "edit"]},
    # Медиапланы (контур аккаунта): реестр и конструктор — раздельно.
    {"key": "media_plans",        "label": "Медиапланы · Реестр",      "group": "Аккаунты", "actions": ["view", "edit", "approve"]},
    {"key": "media_plans_editor", "label": "Медиапланы · Конструктор", "group": "Аккаунты", "actions": ["view", "edit"]},
    {"key": "operations",        "label": "Операции",           "group": "Финансы",   "actions": ["view", "create", "edit", "delete"]},
    {"key": "import",            "label": "Импорт",             "group": "Финансы",   "actions": ["view"]},
    {"key": "counterparties",    "label": "Контрагенты",        "group": "Справочники", "actions": ["view", "edit", "delete", "view_operations"]},
    {"key": "contracts",         "label": "Договоры",           "group": "Справочники", "actions": ["view", "edit"]},
    {"key": "dir_advertisers",   "label": "Рекламодатели",      "group": "Справочники", "actions": ["view", "edit", "delete"]},
    {"key": "dir_agencies",      "label": "Агентства",          "group": "Справочники", "actions": ["view", "edit", "delete"]},
    {"key": "bx_reconcile",      "label": "Сверка с Битриксом", "group": "Справочники", "actions": ["view", "edit"]},
    # Настройки разнесены на отдельные страницы (/settings/*) — по праву на раздел,
    # как справочники. Пользователи и Роли сюда НЕ входят (admin-only, см. выше).
    {"key": "settings_balances",    "label": "Настройки · Остатки",  "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_articles",    "label": "Настройки · Статьи",   "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_pipelines",   "label": "Настройки · Воронки",  "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_services",    "label": "Настройки · Услуги",   "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_field_audit", "label": "Настройки · Сверка полей", "group": "Ядро", "actions": ["view"]},
    {"key": "settings_audit",       "label": "Настройки · Журнал действий", "group": "Ядро", "actions": ["view"]},
    # Бэклог отладки: что держим под наблюдением после больших изменений.
    # Без "delete" осознанно — записи снимаются с наблюдения статусом, а не стиранием:
    # удалённое наблюдение не отличить от «не заводили».
    {"key": "settings_backlog",     "label": "Настройки · Бэклог отладки", "group": "Ядро", "actions": ["view", "create", "edit"]},
]

# Разделы настроек (для фронта: SettingsTabs, редирект, гейт страниц).
SETTINGS_SECTIONS = ("settings_balances", "settings_articles", "settings_pipelines",
                     "settings_services", "settings_field_audit", "settings_audit",
                     "settings_backlog")

# Секции продаж (5-уровневый контроль со свои/все) — для UI-матрицы и gate-хелперов.
SALES_SECTIONS = ("sales_dashboard", "sales_registry", "sales_analytics")

ACTION_FIELDS = {"view": "can_view", "create": "can_create", "edit": "can_edit", "delete": "can_delete", "view_operations": "can_view_operations", "approve": "can_approve"}


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


def require_any_permission(sections, action: str = "view"):
    """Пропускает, если у роли есть can_<action> хотя бы по одной из секций.
    Для эндпойнтов, которые обслуживают несколько страниц (напр. /sales/dashboard
    читают и реестр, и аналитика). Admin всегда проходит."""
    def checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if current_user.role.key == "admin":
            return current_user
        field = ACTION_FIELDS.get(action, "can_view")
        rows = (db.query(RolePermission)
                .filter(RolePermission.role_id == current_user.role_id,
                        RolePermission.section.in_(list(sections))).all())
        if any(bool(getattr(r, field)) for r in rows):
            return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия")
    return checker


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
