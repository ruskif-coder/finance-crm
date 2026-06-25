from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

# Блокировка после неудачных попыток входа — в памяти процесса, по аналогии с
# IMPORT_SYNC_CACHE в operations.py; не переживает перезапуск контейнера.
_LOGIN_ATTEMPTS = {}  # email -> {"count": int, "locked_until": datetime|None}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

def _check_login_lockout(email: str):
    entry = _LOGIN_ATTEMPTS.get(email)
    if entry and entry.get("locked_until") and entry["locked_until"] > datetime.utcnow():
        remaining = int((entry["locked_until"] - datetime.utcnow()).total_seconds() // 60) + 1
        raise HTTPException(status_code=429, detail=f"Слишком много неудачных попыток входа. Попробуйте через {remaining} мин.")

def _register_failed_login(email: str):
    entry = _LOGIN_ATTEMPTS.setdefault(email, {"count": 0, "locked_until": None})
    entry["count"] += 1
    if entry["count"] >= MAX_LOGIN_ATTEMPTS:
        entry["locked_until"] = datetime.utcnow() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        entry["count"] = 0

def _clear_login_attempts(email: str):
    _LOGIN_ATTEMPTS.pop(email, None)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

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
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    from app.audit import log_action  # локальный импорт — избегаем циклической зависимости (audit.py импортирует auth.py)
    from app.permissions import get_permissions_for_user  # тоже локальный — по той же причине (permissions.py импортирует auth.py)

    _check_login_lockout(form_data.username)

    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        _register_failed_login(form_data.username)
        log_action(db, user, "login_failed", entity_type="user", entity_id=user.id if user else None,
                   details=f"Неудачная попытка входа: {form_data.username}")
        raise HTTPException(status_code=400, detail="Неверный email или пароль")
    if not user.is_active:
        log_action(db, user, "login_failed", entity_type="user", entity_id=user.id,
                   details="Попытка входа деактивированного пользователя")
        raise HTTPException(status_code=400, detail="Учётная запись деактивирована")
    _clear_login_attempts(form_data.username)
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