"""Вход в кабинет — ОТДЕЛЬНЫЙ auth-realm, к ролям финмодуля отношения не имеющий.

Свой ключ подписи обязателен, и это не гигиена: с общим ключом токен, выписанный
кабинетом внешнему лицу, был бы валиден и для финмодуля. Ключи разъезжаются по разным
переменным окружения именно затем, чтобы такая подмена не собиралась даже случайно.

Восстановления по почте нет — сброс только админом со стороны ядра (решение владельца
23.08.2026). Внешний контур остаётся без почтового канала восстановления, а вместе с ним
без всего класса атак на него.
"""
import hashlib
import hmac
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


# Болванка для выравнивания времени. Настоящий bcrypt-хеш: проверка по нему стоит те же
# ~200 мс, что и по любому другому, и внешняя сторона не отличает «нет такой учётки» от
# «пароль не подошёл». Тот же приём, что в ядре (`_DUMMY_BCRYPT_HASH`, находка пентеста
# 18.07.2026).
_DUMMY_HASH = bcrypt.hashpw(b"timing_equalizer_dummy_password", bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Тихий False на битом или пустом хеше.

    Проверка прогоняется и для несуществующей учётки — иначе время ответа выдаёт, заведён
    такой адрес или нет. Исключение здесь вернуло бы этот timing-оракул обратно.

    До 31.08.2026 фраза выше была неправдой: на пустом хеше стоял ранний выход, и замер
    показал 0 мс против 212 мс. Теперь пустой хеш прогоняется по болванке — время то же,
    ответ тот же False.
    """
    if not hashed:
        bcrypt.checkpw((plain or "").encode("utf-8")[:MAX_BCRYPT_BYTES],
                       _DUMMY_HASH.encode("utf-8"))
        return False
    try:
        return bcrypt.checkpw((plain or "").encode("utf-8")[:MAX_BCRYPT_BYTES],
                              hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Битый хеш в базе — тоже «нет доступа», и отвечать на него быстрее, чем на
        # настоящий, незачем: разница во времени сама по себе сообщает о состоянии учётки.
        bcrypt.checkpw((plain or "").encode("utf-8")[:MAX_BCRYPT_BYTES],
                       _DUMMY_HASH.encode("utf-8"))
        return False


def password_fingerprint(pw_hash) -> str:
    """Отпечаток текущего хеша пароля. Сменился пароль — токены, выданные раньше, больше
    не принимаются (аудит 23.09.2026, 9.2): до этого сброс пароля менеджером не выкидывал
    сессию площадки ещё 12 часов. HMAC на ключе кабинета — по токену о хеше не узнать."""
    return hmac.new(SECRET_KEY.encode(), (pw_hash or '').encode(),
                    hashlib.sha256).hexdigest()[:16]


def _current_hash(account_id: int):
    db = plain_session()
    try:
        row = db.execute(text("SELECT hashed_password FROM pub.account_v1 WHERE id = :i"),
                         {"i": account_id}).first()
    finally:
        db.close()
    return getattr(row, "hashed_password", None) if row else None


def make_token(account_id: int, email: str, pw_hash=None) -> str:
    # Хеш передаёт вход (строка уже прочитана); без него — читаем сами.
    if pw_hash is None:
        pw_hash = _current_hash(account_id)
    payload = {"sub": str(account_id), "email": email, "realm": "cabinet",
               "pwv": password_fingerprint(pw_hash),
               "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def find_account(email: str):
    """Учётка по адресу. Возвращает строку view или None."""
    db = plain_session()
    try:
        return db.execute(text(
            "SELECT id, email, name, hashed_password, is_active, can_approve, "
            "consent_accepted_at "
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


# Отказ без согласия — строкой-ключом: экран узнаёт его и показывает форму согласия,
# а не «ошибку» (владелец, 24.09.2026).
CONSENT_REQUIRED = "consent_required"


def current_account(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    """Учётка, ПРИНЯВШАЯ согласие на обработку ПДн, — для всех ручек с данными.

    Проверку держит сервер: экран согласия обходится прямым вызовом API. Без согласия
    открыты только две двери, и они берут `current_account_any`.
    """
    row = current_account_any(creds)
    if getattr(row, "consent_accepted_at", None) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CONSENT_REQUIRED)
    return row


def current_account_any(creds: HTTPAuthorizationCredentials = Depends(bearer)):
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
            "SELECT id, email, name, is_active, can_approve, consent_accepted_at, "
            "hashed_password FROM pub.account_v1 WHERE id = :i"),
            {"i": int(data["sub"])}).first()
    finally:
        db.close()
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ закрыт")
    # Пароль сменился после выдачи токена — вход заново (9.2).
    if not hmac.compare_digest(str(data.get("pwv") or ""),
                               password_fingerprint(getattr(row, "hashed_password", None))):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Пароль сменился — войдите заново")
    return row
