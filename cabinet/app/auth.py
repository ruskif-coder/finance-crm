"""Вход в кабинет — ОТДЕЛЬНЫЙ auth-realm, к ролям финмодуля отношения не имеющий.

Свой ключ подписи обязателен, и это не гигиена: с общим ключом токен, выписанный
кабинетом внешнему лицу, был бы валиден и для финмодуля. Ключи разъезжаются по разным
переменным окружения именно затем, чтобы такая подмена не собиралась даже случайно.

Восстановления по почте нет — сброс только админом со стороны ядра (решение владельца
23.08.2026). Внешний контур остаётся без почтового канала восстановления, а вместе с ним
без всего класса атак на него.
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.db import plain_session

SECRET_KEY = os.getenv("CABINET_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("CABINET_SECRET_KEY не задан")
ALGORITHM = "HS256"
TOKEN_HOURS = 12

# bcrypt читает не больше 72 байт — свойство алгоритма. Обрезаем так же, как ядро
# (`backend/app/passwords.py`), иначе длинный пароль не подойдёт к хешу, выданному там.
MAX_BCRYPT_BYTES = 72

bearer = HTTPBearer(auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    """Тихий False на битом или пустом хеше.

    Проверка прогоняется и для несуществующей учётки — иначе время ответа выдаёт, заведён
    такой адрес или нет. Исключение здесь вернуло бы этот timing-оракул обратно.
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw((plain or "").encode("utf-8")[:MAX_BCRYPT_BYTES],
                              hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def make_token(account_id: int, email: str) -> str:
    payload = {"sub": str(account_id), "email": email, "realm": "cabinet",
               "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def find_account(email: str):
    """Учётка по адресу. Возвращает строку view или None."""
    db = plain_session()
    try:
        return db.execute(text(
            "SELECT id, email, name, hashed_password, is_active, can_approve "
            "FROM pub.account_v1 WHERE lower(email) = lower(:e)"), {"e": email}).first()
    finally:
        db.close()


def account_publishers(account_id: int):
    """Площадки учётки. Это и есть область видимости всех остальных запросов."""
    db = plain_session()
    try:
        return db.execute(text(
            "SELECT publisher_id, name, domain, code FROM pub.account_publisher_v1 "
            "WHERE account_id = :a ORDER BY name"), {"a": account_id}).all()
    finally:
        db.close()


def current_account(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    """Учётка из токена. Проверяем ЖИВОСТЬ на каждом запросе, а не только при входе.

    Отключение доступа обязано действовать сразу: иначе выданный на 12 часов токен
    переживает решение админа, и «доступ закрыт» означает «закрыт послезавтра».
    """
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Требуется вход")
    try:
        data = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Сессия истекла — войдите заново")
    if data.get("realm") != "cabinet":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Чужой токен")

    db = plain_session()
    try:
        row = db.execute(text(
            "SELECT id, email, name, is_active, can_approve "
            "FROM pub.account_v1 WHERE id = :i"),
            {"i": int(data["sub"])}).first()
    finally:
        db.close()
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ закрыт")
    return row
