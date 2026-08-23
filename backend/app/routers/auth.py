from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.passwords import hash_password as _hash_password, verify_password as _verify_password
from app.database import get_db
from app.models import User, LoginAttempt
from pydantic import BaseModel
from sqlalchemy import func
import jwt
from jwt.exceptions import InvalidTokenError
from datetime import datetime, timedelta
import time
import threading
import os

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required — check .env")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

# Пентест 2026-07-18, находка #1: без этого хэша ответ на несуществующий email
# приходит за ~9 мс (bcrypt не считается), а на существующий — за ~230 мс, что даёт
# timing-oracle для перечисления учёток. Прогоняем verify_password против фиктивного
# хэша, когда юзер не найден, чтобы время ответа не зависело от существования email.
_DUMMY_BCRYPT_HASH = _hash_password("timing_equalizer_dummy_password")

# Пентест 2026-07-18, находка #2: локаут только по email не мешает password spraying
# (один пароль по многим email). Добавляем per-IP троттлинг /login. In-memory (один
# backend-контейнер), скользящее окно; переживать рестарт не обязано — при рестарте
# счётчик обнуляется, что безопасно (не блокирует легитимных, лишь снимает защиту на миг).
MAX_LOGIN_PER_IP = 20            # попыток с одного IP
LOGIN_IP_WINDOW_SECONDS = 15 * 60
_ip_attempts: dict[str, list[float]] = {}
_ip_lock = threading.Lock()


def _check_ip_rate_limit(ip: str):
    now = time.time()
    with _ip_lock:
        window = [t for t in _ip_attempts.get(ip, []) if now - t < LOGIN_IP_WINDOW_SECONDS]
        _ip_attempts[ip] = window
        if len(window) >= MAX_LOGIN_PER_IP:
            raise HTTPException(status_code=429, detail="Слишком много попыток входа. Попробуйте позже.")
        window.append(now)

# Блокировка входа — состояние хранится в таблице login_attempts (PostgreSQL),
# а не в dict в памяти процесса, поэтому переживает docker restart finance_backend.
# Таблица создаётся автоматически через Base.metadata.create_all() при старте.
# Одна строка на email; при успешном входе счётчик/блокировка сбрасываются (не удаляются).

def _norm_email(email: str) -> str:
    """Нормализация email для поиска/локаута (пентест #3): регистронезависимо + trim,
    чтобы варианты регистра не получали отдельный счётчик локаута и вход работал одинаково."""
    return (email or "").strip().lower()


def _check_login_lockout(db: Session, email: str):
    row = db.query(LoginAttempt).filter(LoginAttempt.email == email).first()
    if row and row.locked_until and row.locked_until > datetime.utcnow():
        remaining = int((row.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много неудачных попыток входа. Попробуйте через {remaining} мин."
        )

def _register_failed_login(db: Session, email: str):
    row = db.query(LoginAttempt).filter(LoginAttempt.email == email).first()
    if not row:
        row = LoginAttempt(email=email, failed_count=0)
        db.add(row)
    row.failed_count += 1
    if row.failed_count >= MAX_LOGIN_ATTEMPTS:
        row.locked_until = datetime.utcnow() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        row.failed_count = 0
    row.updated_at = datetime.utcnow()
    db.commit()

def _clear_login_attempts(db: Session, email: str):
    row = db.query(LoginAttempt).filter(LoginAttempt.email == email).first()
    if row:
        row.failed_count = 0
        row.locked_until = None
        row.updated_at = datetime.utcnow()
        db.commit()

# Имена оставлены прежними: их импортируют users.py и counterparties.py.
# Реализация переехала в app/passwords.py (напрямую bcrypt) — passlib с 2020 года
# не обновлялся, ломался о bcrypt>=4.1 и тянул модуль crypt, удалённый в Python 3.13.
verify_password = _verify_password
get_password_hash = _hash_password

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user

@router.post("/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    from app.audit import log_action  # локальный импорт — избегаем циклической зависимости (audit.py импортирует auth.py)
    from app.permissions import get_permissions_for_user  # тоже локальный — по той же причине (permissions.py импортирует auth.py)

    # per-IP троттлинг (#2). За Caddy реальный IP в X-Forwarded-For; фолбэк — сокет.
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "unknown"))
    _check_ip_rate_limit(client_ip)

    email = _norm_email(form_data.username)
    _check_login_lockout(db, email)

    # Регистронезависимый поиск (#3). Timing-фикс (#1): при отсутствии юзера всё равно
    # прогоняем bcrypt против фиктивного хэша, чтобы время ответа не выдавало наличие email.
    user = db.query(User).filter(func.lower(User.email) == email).first()
    password_ok = verify_password(form_data.password, user.hashed_password) if user else \
        (verify_password(form_data.password, _DUMMY_BCRYPT_HASH) and False)
    if not user or not password_ok:
        _register_failed_login(db, email)
        log_action(db, user, "login_failed", entity_type="user", entity_id=user.id if user else None,
                   details=f"Неудачная попытка входа: {form_data.username}")
        raise HTTPException(status_code=400, detail="Неверный email или пароль")
    if not user.is_active:
        log_action(db, user, "login_failed", entity_type="user", entity_id=user.id,
                   details="Попытка входа деактивированного пользователя")
        raise HTTPException(status_code=400, detail="Учётная запись деактивирована")
    _clear_login_attempts(db, email)
    token = create_access_token({"sub": user.email, "role": user.role.key})
    log_action(db, user, "login_success", entity_type="user", entity_id=user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.key,
        "role_label": user.role.label,
        "is_admin": user.role.key == "admin",
        "permissions": get_permissions_for_user(db, user),
        "name": user.name,
        "consent_required": user.consent_accepted_at is None,
    }

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.permissions import get_permissions_for_user

    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role.key,
        "role_label": current_user.role.label,
        "is_admin": current_user.role.key == "admin",
        "permissions": get_permissions_for_user(db, current_user),
    }


class _PwdCheck(BaseModel):
    password: str


@router.post("/verify-password")
def verify_current_password(body: _PwdCheck,
                            current_user: User = Depends(get_current_user)):
    """Подтверждение действия повторным вводом пароля (напр. удаление строки плана).
    Возвращает {ok: True} при совпадении, иначе 401 — фронт по этому гейту пропускает
    деструктивное действие. Пароль проверяется, но не логируется и никуда не пишется."""
    if not verify_password(body.password or "", current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный пароль")
    return {"ok": True}


@router.post("/accept-consent")
def accept_consent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """152-ФЗ: фиксирует момент принятия пользователем согласия на обработку персональных данных."""
    from app.audit import log_action
    current_user.consent_accepted_at = datetime.utcnow()
    db.commit()
    log_action(db, current_user, "consent_accepted", entity_type="user", entity_id=current_user.id,
               details="Пользователь принял согласие на обработку персональных данных (152-ФЗ)")
    return {"ok": True}
