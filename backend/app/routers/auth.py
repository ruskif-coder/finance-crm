from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.passwords import hash_password as _hash_password, verify_password as _verify_password
from app.database import get_db
from app.models import User, LoginAttempt
from pydantic import BaseModel
from sqlalchemy import func
import hashlib
import hmac
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
# Потолок числа отслеживаемых адресов. Он тут не для экономии памяти «на всякий случай»:
# ключ словаря приходит СНАРУЖИ (заголовок запроса), и без потолка неаутентифицированный
# запрос наращивает память процесса неограниченно — при `mem_limit: 512m` это отказ в
# обслуживании одним циклом curl. Дефект найден при разборе внешнего аудита 11.09.2026:
# сам обход лимита (F1-01) был замечен, а вот его соседняя половина — нет.
MAX_TRACKED_IPS = 10_000
_ip_attempts: dict[str, list[float]] = {}
_ip_lock = threading.Lock()


def _prune_ip_attempts(now: float) -> None:
    """Выбросить адреса, у которых окно целиком протухло.

    Раньше чистилось ТОЛЬКО окно спрашиваемого адреса, а сам ключ оставался навсегда.
    Зовётся под `_ip_lock` и только при переполнении — обходить весь словарь на каждом
    входе незачем, а при переполнении это амортизированно дёшево.
    """
    stale = [ip for ip, ts in _ip_attempts.items()
             if not ts or now - ts[-1] >= LOGIN_IP_WINDOW_SECONDS]
    for ip in stale:
        del _ip_attempts[ip]
    # Если протухших не хватило — словарь забит активными адресами, и это уже похоже на
    # распределённый перебор. Держим самые свежие: у старых окно всё равно вот-вот
    # истечёт, а терять защиту у того, кто стучится прямо сейчас, нельзя.
    if len(_ip_attempts) > MAX_TRACKED_IPS:
        newest = sorted(_ip_attempts.items(), key=lambda kv: kv[1][-1], reverse=True)
        _ip_attempts.clear()
        _ip_attempts.update(dict(newest[:MAX_TRACKED_IPS]))


def _check_ip_rate_limit(ip: str):
    now = time.time()
    with _ip_lock:
        window = [t for t in _ip_attempts.get(ip, []) if now - t < LOGIN_IP_WINDOW_SECONDS]
        _ip_attempts[ip] = window
        if len(_ip_attempts) > MAX_TRACKED_IPS:
            _prune_ip_attempts(now)
            window = _ip_attempts.setdefault(ip, window)
        if len(window) >= MAX_LOGIN_PER_IP:
            raise HTTPException(status_code=429, detail="Слишком много попыток входа. Попробуйте позже.")
        window.append(now)


def client_ip(request) -> str:
    """Адрес клиента ДЛЯ ТРОТТЛИНГА — из доверенного звена, а не из первого попавшегося.

    `X-Forwarded-For` — список, который дополняет КАЖДЫЙ прокси на пути. Клиент волен
    прислать его сам, и всё, что он прислал, окажется СЛЕВА; правее допишет Caddy — то,
    что он увидел на сокете. Значит доверять можно только ПОСЛЕДНЕМУ элементу.

    До 11.09.2026 брался первый: подставив свой заголовок, любой желающий получал новый
    счётчик на каждую попытку и проходил мимо лимита 20/15 мин (F1-01 внешнего аудита).

    Допущение, на котором это держится: перед бэкендом ровно один наш прокси. Оно верно
    по построению — порт бэкенда слушает только `127.0.0.1`, и снаружи в него никто, кроме
    Caddy, не попадает. Изменится схема — менять и здесь.
    """
    chain = [x.strip() for x in (request.headers.get("x-forwarded-for") or "").split(",")]
    chain = [x for x in chain if x]
    if chain:
        return chain[-1]
    return request.client.host if request.client else "unknown"

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

# Отказ без согласия на обработку ПДн — строкой-ключом: экран узнаёт его и ведёт на
# форму согласия (аудит 23.09.2026, 9.7; решение владельца 24.09.2026 — как в кабинете).
CONSENT_REQUIRED = "consent_required"


def password_fingerprint(user) -> str:
    """Отпечаток ТЕКУЩЕГО хеша пароля — для токена.

    Смена пароля меняет хеш, а с ним отпечаток: все выданные раньше токены перестают
    приниматься. До этого токен жил свои 8 часов и после сброса пароля, то есть сброс не
    выкидывал украденную сессию (аудит 23.09.2026, 9.2). Схему базы не трогает. HMAC на
    секрете ядра — чтобы по токену нельзя было ничего узнать о хеше.
    """
    return hmac.new(SECRET_KEY.encode(), (user.hashed_password or '').encode(),
                    hashlib.sha256).hexdigest()[:16]


def token_claims(user) -> dict:
    return {"sub": user.email, "role": user.role.key, "pwv": password_fingerprint(user)}


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Пользователь, ПРИНЯВШИЙ согласие на обработку ПДн, — для всех ручек с данными.

    Без согласия открыты только «кто я» и само принятие (`get_current_user_any`):
    проверка на одном экране входа обходилась прямым вызовом API (аудит, 6.M8).
    """
    user = get_current_user_any(token, db)
    if user.consent_accepted_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CONSENT_REQUIRED)
    return user


def get_current_user_any(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Пользователь из токена — живой, с неизменившимся паролем. Согласие не проверяет."""
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
    # Пароль сменился после выдачи токена — токен недействителен (9.2). Токен без
    # отпечатка — выданный до этой правки: один повторный вход после выкладки.
    if not hmac.compare_digest(str(payload.get("pwv") or ""), password_fingerprint(user)):
        raise credentials_exception
    return user

@router.post("/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    from app.audit import log_action  # локальный импорт — избегаем циклической зависимости (audit.py импортирует auth.py)
    from app.permissions import get_permissions_for_user  # тоже локальный — по той же причине (permissions.py импортирует auth.py)

    # per-IP троттлинг (#2). Адрес берётся из ПОСЛЕДНЕГО звена цепочки — см. client_ip.
    _check_ip_rate_limit(client_ip(request))

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
    token = create_access_token(token_claims(user))
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
def get_me(current_user: User = Depends(get_current_user_any), db: Session = Depends(get_db)):
    from app.permissions import get_permissions_for_user

    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role.key,
        "role_label": current_user.role.label,
        "is_admin": current_user.role.key == "admin",
        "permissions": get_permissions_for_user(db, current_user),
        "consent_required": current_user.consent_accepted_at is None,
    }


class _PwdCheck(BaseModel):
    password: str


@router.post("/verify-password")
def verify_current_password(body: _PwdCheck,
                            current_user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Подтверждение действия повторным вводом пароля (напр. удаление строки плана).
    Возвращает {ok: True} при совпадении, иначе 403 — фронт по этому гейту пропускает
    деструктивное действие. Пароль проверяется, но не логируется и никуда не пишется.

    Попытки — общим со входом счётчиком (аудит 23.09.2026, 9.3): без него пароль учётки
    подбирался здесь с чужим токеном в обход блокировки `/login`."""
    email = _norm_email(current_user.email)
    _check_login_lockout(db, email)
    if not verify_password(body.password or "", current_user.hashed_password):
        _register_failed_login(db, email)
        # 403, а не 401: 401 фронт читает как «сессия истекла» и выкидывает на вход после
        # одной опечатки в окне подтверждения (ревью 24.09.2026).
        raise HTTPException(status_code=403, detail="Неверный пароль")
    _clear_login_attempts(db, email)
    return {"ok": True}


@router.post("/accept-consent")
def accept_consent(
    current_user: User = Depends(get_current_user_any),
    db: Session = Depends(get_db)
):
    """152-ФЗ: фиксирует момент принятия пользователем согласия на обработку персональных данных."""
    from app.audit import log_action
    current_user.consent_accepted_at = datetime.utcnow()
    db.commit()
    log_action(db, current_user, "consent_accepted", entity_type="user", entity_id=current_user.id,
               details="Пользователь принял согласие на обработку персональных данных (152-ФЗ)")
    return {"ok": True}
