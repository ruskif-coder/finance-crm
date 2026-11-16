from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import RolePermission, User, Role, AuditLog
from app.audit import log_action, require_admin
from app.permissions import require_permission
from app.routers.auth import get_password_hash
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime, timedelta, time as dt_time
from app.timez import MSK_OFFSET
from app import users_events

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
    """Профили уведомлений для экрана пользователей. Отдельный лёгкий список, чтобы страница пользователей не тянула
    настройки уведомлений целиком. `by_role` — с какого профиля начинает новый сотрудник роли (16.11.2026: новая строка
    на экране показывает его сразу, а не после сохранения)."""
    from app.notify.models import NotificationProfile
    rows = db.query(NotificationProfile).order_by(NotificationProfile.id).all()
    starts = {r.key: _start_profile_id(db, r) for r in db.query(Role).all()}
    return {"profiles": [{"id": p.id, "label": p.label, "is_default": p.is_default} for p in rows],
            "by_role": {k: v for k, v in starts.items() if v}}


def _start_profile_id(db: Session, role: Role) -> Optional[int]:
    from app.notify.models import NotificationProfile
    from app.notify.seed_profiles import start_profile_key
    key = start_profile_key(role.key, role.staff_group)
    if not key:
        return None
    prof = db.query(NotificationProfile).filter(NotificationProfile.key == key).first()
    return prof.id if prof else None


def _create(db: Session, current_user, data: UserCreate) -> tuple:
    """Создать пользователя без коммита: (пользователь, строка журнала). Общая для ручки и пакета."""
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Укажите имя")
    email = (data.email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Некорректный email")
    existing = db.query(User).filter(User.email == email).first()
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
    profile_id = data.notification_profile_id or _start_profile_id(db, role)

    user = User(
        name=data.name.strip(),
        email=email,
        hashed_password=get_password_hash(data.password),
        role_id=role.id,
        notification_profile_id=profile_id,
    )
    db.add(user)
    db.flush()
    return user, f"Создан пользователь {user.name} ({user.email}), роль {role.label}"


@router.post("/")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    user, details = _create(db, current_user, data)
    db.commit()
    db.refresh(user)
    log_action(db, current_user, "create_user", entity_type="user", entity_id=user.id, details=details)
    users_events.created(db, current_user, user)
    return {"id": user.id, "message": "Пользователь создан"}


def _update(db: Session, current_user, user: User, data: UserUpdate) -> list:
    """Применить правку без коммита; вернуть список изменений для журнала. Общая для ручки и пакета."""
    user_id = user.id
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
        # Отзыв токенов, выданных до смены: иначе «выключил → включил» оживлял бы старые (аудит 06.10.2026)
        user.token_epoch = (user.token_epoch or 0) + 1

    if data.password:
        if len(data.password) < 8:
            raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
        changes.append("пароль изменён")
        user.hashed_password = get_password_hash(data.password)

    # Привязки к сотруднику Битрикса (bitrix_user_id) в форме нет с 03.10.2026 — Битрикс
    # больше не источник. Колонка в users остаётся как история.

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

    return changes


def _after_update(db: Session, current_user, user: User, changes: list) -> None:
    # Смена email/пароля админом снимает локаут по НОВОМУ email: иначе пользователь мог
    # остаться заблокированным на свежих учётных данных из-за прежних неудачных попыток
    # (например, этот email вводили с неверным паролем ещё до его назначения).
    if any(c.startswith("email:") or c == "пароль изменён" for c in changes):
        from app.routers.auth import _clear_login_attempts, _norm_email
        _clear_login_attempts(db, _norm_email(user.email))
    if changes:
        log_action(db, current_user, "update_user", entity_type="user", entity_id=user.id,
                   details=f"{user.name} ({user.email}): " + "; ".join(changes))


@router.put("/batch")
def save_users_batch(data: "UsersBatch", db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Все правки экрана «Пользователи» одним запросом (макет 16.11.2026). Объявлена ДО `/{user_id}`: иначе «batch»
    разбирался бы как номер пользователя и отвечал 422."""
    return _save_batch(db, current_user, data)


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
    before = users_events.before_of(db, user)
    changes = _update(db, current_user, user, data)
    db.commit()
    _after_update(db, current_user, user, changes)
    users_events.updated(db, current_user, user, before, changes)
    return {"message": "Пользователь обновлён"}


def _delete(db: Session, current_user, user: User) -> str:
    """Удаление пользователя (2026-07-16). Только деактивированных — как страховка от
    случайного удаления рабочей учётки. Пользователь с созданными операциями не удаляется
    (created_by — авторство должно сохраниться), его оставляем деактивированным.
    Записи аудита сохраняются: user_id обнуляется, user_name денормализован и остаётся."""
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Сначала деактивируйте пользователя")

    from app.models import Operation
    op_count = db.query(Operation).filter(Operation.created_by == user.id).count()
    if op_count:
        raise HTTPException(
            status_code=400,
            detail=f"У пользователя {op_count} созданных операций — удалить нельзя, оставьте деактивированным"
        )

    # Журнал действий не трогаем: отвязываем user_id, имя остаётся в денормализованном user_name
    db.query(AuditLog).filter(AuditLog.user_id == user.id).update({"user_id": None})

    details = f"Удалён пользователь {user.name} ({user.email})"
    db.delete(user)
    db.flush()
    return details


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    who = f"{user.name} ({user.email})"
    details = _delete(db, current_user, user)
    db.commit()
    log_action(db, current_user, "delete_user", entity_type="user", entity_id=user_id, details=details)
    users_events.deleted(db, current_user, user_id, who)
    return {"message": "Пользователь удалён"}


# ── Пакетное сохранение (экран «Пользователи» по макету 16.11.2026) ──────────────────────────────────────────────────
class UserPatch(BaseModel):
    """Правка одной строки экрана: новая (`new`), удаление (`delete`) или изменение полей существующей."""
    id: Optional[int] = None
    new: bool = False
    delete: bool = False
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    notification_profile_id: Optional[int] = None
    password: Optional[str] = None


class UsersBatch(BaseModel):
    changes: List[UserPatch]


def _row_label(p: UserPatch, user: Optional[User]) -> str:
    return (p.name or "").strip() or (user.name if user else "") or (p.email or "").strip() or "новая строка"


def _apply_patch(db: Session, current_user, p: UserPatch, journal: list, created: list) -> None:
    if p.new:
        user, details = _create(db, current_user, UserCreate(
            name=p.name or "", email=p.email or "", password=p.password or "", role=p.role or "viewer",
            notification_profile_id=p.notification_profile_id))
        if p.is_active is False:
            user.is_active = 0
            details += ", деактивирован"
        created.append(user.id)
        journal.append(("create", user, details, None))
        return
    user = db.query(User).filter(User.id == p.id).first() if p.id else None
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if p.delete:
        uid, who = user.id, f"{user.name} ({user.email})"
        journal.append(("delete", uid, _delete(db, current_user, user), who))
        return
    before = users_events.before_of(db, user)
    journal.append(("update", user, _update(db, current_user, user, UserUpdate(
        name=p.name, email=p.email, role=p.role, is_active=p.is_active, password=p.password,
        notification_profile_id=p.notification_profile_id)), before))


def _save_batch(db: Session, current_user, data: UsersBatch) -> dict:
    """Все правки экрана — одной транзакцией. Не прошла одна — не применяется ничего, ответ называет строку.
    Проверки — те же функции, что у ручек «по одному» (`_create`/`_update`/`_delete`)."""
    if not data.changes:
        raise HTTPException(status_code=400, detail="Нечего сохранять")
    journal, created = [], []     # журнал — в порядке строк запроса
    try:
        for p in data.changes:
            try:
                _apply_patch(db, current_user, p, journal, created)
            except HTTPException as e:
                user = db.query(User).filter(User.id == p.id).first() if p.id and not p.new else None
                raise HTTPException(status_code=e.status_code, detail=f"{_row_label(p, user)}: {e.detail}") from e
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Журнал и уведомления — после коммита и в порядке строк запроса: не сохранилось — не о чем сообщать.
    for kind, a, b, c in journal:
        if kind == "create":
            log_action(db, current_user, "create_user", entity_type="user", entity_id=a.id, details=b)
            users_events.created(db, current_user, a)
        elif kind == "update":
            _after_update(db, current_user, a, b)
            users_events.updated(db, current_user, a, c, b)
        else:
            log_action(db, current_user, "delete_user", entity_type="user", entity_id=a, details=b)
            users_events.deleted(db, current_user, a, c)
    return {"saved": len(data.changes), "created": created}


# Подписи действий — в `app/audit_labels.py` (одна точка на журнал).
from app.audit_labels import ACTION_LABELS  # noqa: E402


@router.get("/audit-log/")
def get_audit_log(
    skip: int = 0,
    limit: int = 100,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_audit", "view"))
):
    query = db.query(AuditLog)
    # Поиск по тексту (владелец 01.10.2026): детали и имя пользователя, без учёта
    # регистра. Спецсимволы LIKE экранируются — «%» в запросе ищется как знак.
    if q and q.strip():
        pat = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(AuditLog.details.ilike(pat, escape="\\"),
                                 AuditLog.user_name.ilike(pat, escape="\\")))
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    # Человек выбирает МОСКОВСКИЙ календарный день, а `created_at` лежит в UTC. Прямое
    # сравнение брало сутки по Гринвичу: события с 00:00 до 03:00 по Москве уезжали в
    # следующий день, а вечерние с 21:00 приходили из предыдущего. Три часа журнала
    # каждые сутки лежали не в той дате — и выглядело это не ошибкой, а затишьем.
    # Поэтому границу сдвигаем на пояс, а не колонку: колонка остаётся UTC.
    if date_from:
        query = query.filter(
            AuditLog.created_at >= datetime.combine(date_from, dt_time())
            - timedelta(hours=MSK_OFFSET))
    if date_to:
        query = query.filter(
            AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), dt_time())
            - timedelta(hours=MSK_OFFSET))

    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    # Что именно изменили — код и название сделки, имя площадки и т. п. (владелец,
    # 24.09.2026): номер из базы человеку ничего не говорит. Считается при показе.
    from app.audit_objects import describe
    objects = describe(db, [(r.entity_type, r.entity_id) for r in rows])

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
                "object": objects.get((r.entity_type, r.entity_id)),
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }
