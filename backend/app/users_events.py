# -*- coding: utf-8 -*-
"""Уведомления о действиях администратора над пользователями (экран «Пользователи», 16.11.2026).

Зовётся ПОСЛЕ коммита — не сохранилось, сообщать не о чем. Пароль не попадает ни в одно уведомление: он показывается
администратору на экране один раз. Сбой уведомления не отменяет сохранённого — пишется в лог.
"""
import logging

from sqlalchemy.orm import Session

from app.models import Role, User

log = logging.getLogger("finance.users")
LINK = "/settings/users"


def _emit(db: Session, key: str, actor, **kw) -> None:
    from app.notify import bus
    try:
        bus.emit(db, key, actor=actor, entity_type="user", **kw)
    except Exception:  # noqa: BLE001 — уведомление справка, правка уже сохранена
        log.exception("уведомление %s не отправлено", key)


def _who(user: User) -> str:
    return f"{user.name} ({user.email})"


def created(db: Session, actor, user: User) -> None:
    role = db.get(Role, user.role_id)
    _emit(db, "user_created", actor, title=f"Заведён пользователь: {_who(user)}",
          body=f"Роль — {role.label if role else '?'}. Заводил {getattr(actor, 'name', '?')}.", link=LINK,
          entity_id=user.id, ctx={"user": user})
    _emit(db, "user_welcome", actor, title="Вам заведена учётная запись в SIMB-AD ERP",
          body=(f"Здравствуйте, {user.name}! Для вас заведена учётная запись. Логин — ваш email {user.email}. "
                "Пароль вам сообщит администратор; после входа его можно сменить."),
          link="/login", entity_id=user.id, ctx={"user": user}, user_ids=[user.id])


def updated(db: Session, actor, user: User, before: dict, changes: list) -> None:
    """`before` — роль (ключ и подпись) и активность ДО правки; `changes` — строки журнала из `_update`."""
    role = db.get(Role, user.role_id)
    if "пароль изменён" in changes:
        _emit(db, "user_password_reset", actor, title="Ваш пароль сброшен администратором",
              body=f"{getattr(actor, 'name', 'Администратор')} задал новый пароль, старый больше не действует. Новый пароль "
                   "сообщит администратор.", link="/", entity_id=user.id, ctx={"user": user})
    if role and role.key != before["role_key"]:
        _emit(db, "user_role_changed", actor, title=f"Изменена роль: {_who(user)}",
              body=f"{before['role_label']} → {role.label}. Новые права действуют после повторного входа.", link=LINK,
              entity_id=user.id, ctx={"user": user})
        if "admin" in (role.key, before["role_key"]):
            what = "назначена" if role.key == "admin" else "снята"
            _emit(db, "user_admin_role", actor, title=f"Роль «Администратор» {what}: {_who(user)}",
                  body=f"{before['role_label']} → {role.label}. Сделал {getattr(actor, 'name', '?')}.", link=LINK,
                  entity_id=user.id, ctx={"user": user})
    if bool(user.is_active) != before["active"]:
        what = "возвращён доступ" if user.is_active else "деактивирован"
        _emit(db, "user_activity_changed", actor, title=f"Пользователь {what}: {_who(user)}",
              body=("Вход снова открыт." if user.is_active else "Вход закрыт, данные остались."), link=LINK,
              entity_id=user.id, ctx={"user": user})


def deleted(db: Session, actor, user_id: int, who: str) -> None:
    _emit(db, "user_deleted", actor, title=f"Пользователь удалён: {who}",
          body=f"Удалил {getattr(actor, 'name', '?')}. Записи журнала действий остались с его именем.", link=LINK,
          entity_id=user_id)


def before_of(db: Session, user: User) -> dict:
    role = db.get(Role, user.role_id)
    return {"role_key": role.key if role else None, "role_label": role.label if role else "?", "active": bool(user.is_active)}
