from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RolePermission, User, Role, AuditLog
from app.audit import log_action, require_admin
from app.permissions import require_permission
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
    # Профиль уведомлений: необязателен — если не прислан, выводится из роли ниже.
    # Поле обязано быть объявлено здесь: create_user читает data.notification_profile_id,
    # а в pydantic v2 обращение к необъявленному полю — AttributeError, то есть 500
    # на КАЖДОМ создании пользователя (так и было до 2026-08-20).
    notification_profile_id: Optional[int] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    bitrix_user_id: Optional[str] = None  # "" → отвязать, None → не трогать
    # Профиль уведомлений (app/notify): 0 → сбросить на профиль по умолчанию.
    # Сознательно НЕ выводится из роли — роль отвечает за доступ, профиль за рассылку.
    notification_profile_id: Optional[int] = None


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
            "bitrix_user_id": u.bitrix_user_id,
            "notification_profile_id": u.notification_profile_id,
        }
        for u in users
    ]


@router.get("/access-overview")
def access_overview(db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    """Кто вообще имеет доступ — оба контура одним ответом, только на чтение.

    Учётки паблишеров ЖИВУТ ОТДЕЛЬНО и жить вместе не могут: сервис кабинета работает
    под ролью БД без прав на `public`, и перенос его учёток в `users` потребовал бы
    выдать этой роли доступ к таблице ядра — то есть распустить изоляцию, на которой
    весь внешний контур и стоит. Плюс несовместимые модели прав: у пользователя ядра
    роль на 34 секции, у паблишера — `can_approve` и список площадок; в общей таблице
    каждая проверка прав должна была бы помнить «а это не паблишер ли», и дыра появится
    там, где однажды забудут. И `admin` обходит проверки безусловно — неверно
    проставленная роль у внешнего лица открыла бы ему всё.

    Но у раздельного хранения была одна честная цена: на вопрос «у кого есть доступ»
    стало два ответа в двух местах. Эта ручка её и закрывает — сводит ВИДИМОСТЬ, не
    трогая хранение. Ничего не изменяет: правки идут каждая в свой раздел.
    """
    from app.cabinet.models import Cabinet, CabinetAccount
    from app.cabinet.scope import visible_publisher_ids

    core = []
    for u in db.query(User).order_by(User.created_at).all():
        core.append({
            "contour": "ядро",
            "name": u.name,
            "email": u.email,
            "access": u.role.label,
            "is_active": bool(u.is_active),
            "last_login_at": None,
            # Сколько секций реально открыто. У админа проверок нет вообще — это не
            # «много прав», это другой режим, и число здесь солгало бы.
            "scope": ("все разделы (проверки не проходит)" if u.role.key == "admin"
                      else f"{db.query(RolePermission).filter(RolePermission.role_id == u.role_id, RolePermission.can_view == 1).count()} разделов"),
        })

    outer = []
    for a in (db.query(CabinetAccount, Cabinet)
              .outerjoin(Cabinet, Cabinet.id == CabinetAccount.cabinet_id)
              .order_by(CabinetAccount.id).all()):
        acc, cab = a
        # Считаем от КАБИНЕТА, а не по личному списку: он заморожен, и сводка доступа,
        # построенная на нём, показывала бы не то, что человек на самом деле видит.
        # `None` от `visible_publisher_ids` — служебный кабинет: он связей не хранит, и
        # «0 площадок» здесь означало бы ровно обратное правде.
        ids = visible_publisher_ids(db, cab)
        scope_text = "все площадки" if ids is None else f"{len(ids)} площадок"
        outer.append({
            "contour": "кабинет",
            "name": acc.name,
            "email": acc.email,
            "access": (cab.name if cab else "— без кабинета —"),
            "is_active": bool(acc.is_active),
            "last_login_at": acc.last_login_at,
            "scope": scope_text + ("" if acc.can_approve else ", только просмотр"),
        })

    return {"rows": core + outer,
            "core": len(core), "outer": len(outer),
            # Пересечение почт между контурами — его быть не должно. Один и тот же адрес
            # в обоих означает, что человек заведён и внутрь, и наружу: это либо ошибка,
            # либо решение, которое надо принимать осознанно.
            "shared_emails": [r["email"] for r in outer
                              if r["email"].lower() in {c["email"].lower() for c in core}]}


@router.get("/notification-profiles")
def notification_profiles(db: Session = Depends(get_db),
                          current_user: User = Depends(require_admin)):
    """Профили уведомлений для селектора в карточке пользователя. Отдельный лёгкий
    список, чтобы страница пользователей не тянула настройки уведомлений целиком."""
    from app.notify.models import NotificationProfile
    rows = db.query(NotificationProfile).order_by(NotificationProfile.id).all()
    return [{"id": p.id, "label": p.label, "is_default": p.is_default} for p in rows]


@router.get("/bitrix-directory")
def bitrix_directory(current_user: User = Depends(require_admin)):
    """Список сотрудников Битрикса для селектора привязки в настройках."""
    from app.bitrix_api import list_bitrix_users
    try:
        # active_only=False — уволенные (неактивные) тоже нужны для привязки исторических reps;
        # фронт помечает их «(уволен)».
        return {"items": list_bitrix_users(active_only=False)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Битрикс недоступен: {e}")


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

    # Профиль уведомлений: взят из запроса, иначе выведен из роли по стартовой
    # раскладке. Без этого новый сотрудник заводился с NULL и не попадал ни в один
    # профиль — а в настройках уведомлений все профили показывали «0 человек»,
    # хотя людей в системе полтора десятка.
    profile_id = data.notification_profile_id or None
    if not profile_id:
        from app.notify.seed_profiles import ROLE_TO_PROFILE
        from app.notify.models import NotificationProfile
        key = ROLE_TO_PROFILE.get(role.key)
        if key:
            prof = db.query(NotificationProfile).filter(NotificationProfile.key == key).first()
            profile_id = prof.id if prof else None

    user = User(
        name=data.name,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role_id=role.id,
        notification_profile_id=profile_id,
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

    if data.email is not None and data.email != user.email:
        new_email = data.email.strip()
        if not new_email or "@" not in new_email:
            raise HTTPException(status_code=400, detail="Некорректный email")
        dup = db.query(User).filter(User.email == new_email, User.id != user_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="Email уже занят другим пользователем")
        changes.append(f"email: {user.email} → {new_email}")
        user.email = new_email

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

    if data.bitrix_user_id is not None:
        new_bx = data.bitrix_user_id.strip() or None
        if new_bx != user.bitrix_user_id:
            changes.append(f"Битрикс-привязка: {user.bitrix_user_id or '—'} → {new_bx or '—'}")
            user.bitrix_user_id = new_bx

    if data.notification_profile_id is not None:
        from app.notify.models import NotificationProfile
        new_pid = data.notification_profile_id or None        # 0 → сброс на профиль по умолчанию
        if new_pid and not db.query(NotificationProfile).filter(
                NotificationProfile.id == new_pid).first():
            raise HTTPException(status_code=400, detail="Профиль уведомлений не найден")
        if new_pid != user.notification_profile_id:
            labels = dict(db.query(NotificationProfile.id, NotificationProfile.label).all())
            changes.append("профиль уведомлений: "
                           f"{labels.get(user.notification_profile_id, '— по умолчанию')} → "
                           f"{labels.get(new_pid, '— по умолчанию')}")
            user.notification_profile_id = new_pid

    db.commit()

    # Смена email/пароля админом снимает лок­аут по НОВОМУ email: иначе пользователь мог
    # остаться заблокированным на свежих учётных данных из-за прежних неудачных попыток
    # (например, этот email вводили с неверным паролем ещё до его назначения).
    if any(c.startswith("email:") or c == "пароль изменён" for c in changes):
        from app.routers.auth import _clear_login_attempts, _norm_email
        _clear_login_attempts(db, _norm_email(user.email))

    if changes:
        log_action(db, current_user, "update_user", entity_type="user", entity_id=user.id,
                   details=f"{user.name} ({user.email}): " + "; ".join(changes))

    return {"message": "Пользователь обновлён"}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Удаление пользователя (2026-07-16). Только деактивированных — как страховка от
    случайного удаления рабочей учётки. Пользователь с созданными операциями не удаляется
    (created_by — авторство должно сохраниться), его оставляем деактивированным.
    Записи аудита сохраняются: user_id обнуляется, user_name денормализован и остаётся."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Сначала деактивируйте пользователя")

    from app.models import Operation
    op_count = db.query(Operation).filter(Operation.created_by == user_id).count()
    if op_count:
        raise HTTPException(
            status_code=400,
            detail=f"У пользователя {op_count} созданных операций — удалить нельзя, оставьте деактивированным"
        )

    # Журнал действий не трогаем: отвязываем user_id, имя остаётся в денормализованном user_name
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update({"user_id": None})

    name, email = user.name, user.email
    db.delete(user)
    db.commit()

    log_action(db, current_user, "delete_user", entity_type="user", entity_id=user_id,
               details=f"Удалён пользователь {name} ({email})")
    return {"message": "Пользователь удалён"}


ACTION_LABELS = {
    # Приложения к договору (05–06.09.2026) и демо-стенд DSP. Без подписи журнал
    # показывает сырой ключ вида `annex_confirm` — строка есть, а прочесть её нельзя.
    "annex_create": "Черновик приложения к договору",
    "annex_edit": "Черновик приложения изменён",
    "annex_confirm": "Приложение к договору выпущено",
    "annex_start_no": "Стартовый номер приложений по договору",
    "annex_template_create": "Формулировка услуги заведена",
    "annex_template_edit": "Формулировка услуги изменена",
    # Админка трафика (каталог блоков) — тоже без подписей до 06.09.2026.
    "traffic_catalog_code_edit": "Код площадки изменён",
    "traffic_catalog_surface_add": "Поверхность площадки добавлена",
    "traffic_catalog_surface_edit": "Поверхность площадки изменена",
    "traffic_catalog_block_add": "Рекламный блок добавлен",
    "traffic_catalog_block_edit": "Рекламный блок изменён",
    "traffic_catalog_block_delete": "Рекламный блок удалён",
    "counterparty_signer": "Подписант контрагента",
    "traffic_creative_script": "Скрипт, вшиваемый в креатив",
    "import_apply": "Импорт операций из файла",
    "ord_resolve_submission": "Разбор зависшей отправки в ОРД",
    "weborama_provision": "Пиксели Weborama по РК",
    "dsp_provision": "Выгрузка креативов РК в DSP",
    "dsp_demo_campaign": "DSP демо: кампания заведена",
    "dsp_demo_creative": "DSP демо: креатив заведён",
    "dsp_demo_status": "DSP демо: статус кампании",
    "dsp_demo_plan": "DSP демо: план кампании",
    "dsp_demo_targeting": "DSP демо: таргетинг",
    "verify_media_plan": "МП проверен",
    "traffic_dashboard_sync": "Обновление РК из сделок",
    "deal_weborama_pixel": "Доп. параметр РК: пиксель Weborama",
    "deal_verifier_shows": "Ручные показы Weborama на сверке",
    "cabinet_notify_toggle": "Рассылка площадкам: вид включён или выключен",
    "cabinet_notify_hours": "Рассылка площадкам: тихие часы и час дайджеста",
    "targeting_link": "Ссылка нацеливания выпущена",
    "mail_settings": "Настройки почты изменены",
    "mail_shell": "Правка оболочки письма",
    "mail_card_text": "Правка текста карточки уведомления",
    "mail_template": "Шаблон письма изменён",
    "mail_test": "Проверочное письмо отправлено",
    "ord_sync_kktu": "Заливка справочника ККТУ из ОРД",
    "ord_initial_delete": "Чистка зеркала: удаление изначальных договоров",
    "bug_report_new": "Заявка о сбое принята",
    "bug_report_status": "Заявка о сбое: смена статуса",
    "bug_report_backlog": "Из заявки заведено наблюдение",
    "maintenance_on": "Объявлено техобслуживание",
    "maintenance_off": "Техобслуживание снято",
    "ord_sync_clients": "Сверка юрлиц с ОРД",
    "ord_sync_contracts": "Сверка договоров с ОРД",
    "ord_register_final": "Договор зарегистрирован в ОРД",
    "ord_register_initial": "Изначальный договор заведён в ОРД",
    "ord_attach_initial": "Изначальный прикреплён к доходному",
    "self_promo_on": "Присвоен статус «самореклама»",
    "self_promo_off": "Снят статус «самореклама»",
    "media_plan_change_note": "Причина изменений МП",
    "deal_title_from_mp": "Название сделки из медиаплана",
    "login_success": "Вход выполнен",
    "login_failed": "Неудачный вход",
    "create_user": "Создание пользователя",
    "update_user": "Изменение пользователя",
    "delete_user": "Удаление пользователя",
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
    current_user: User = Depends(require_permission("settings_audit", "view"))
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
