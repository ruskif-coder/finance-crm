"""Канал доставки Telegram.

Библиотек для бота не тянем — это два HTTP-запроса через httpx, который уже есть.

Конфигурация: TELEGRAM_BOT_TOKEN в .env (не коммитится). Без токена канал считается
ненастроенным: сообщения не теряются, а ложатся в журнал отправок статусом queued —
уйдут после настройки командой flush, а не пропадут молча.

Привязка: пользователь жмёт «Привязать» → получает код → отправляет боту `/start <код>`.
Бот присылает апдейт на вебхук, мы находим код и запоминаем chat_id. Пароли и токены
пользователя при этом нигде не участвуют.
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import httpx

API = "https://api.telegram.org/bot{token}/{method}"
LINK_CODE_TTL_MIN = 30


def bot_token() -> Optional[str]:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip() or None


def configured() -> bool:
    return bot_token() is not None


_USERNAME_CACHE: dict = {}


def _clean_name(raw: str) -> Optional[str]:
    """Из того, что написали в .env, достать голый юзернейм.

    Пишут по-разному: `@SimbAD_alert_bot`, `SimbAD_alert_bot`, целиком ссылкой
    `https://t.me/SimbAD_alert_bot`. Все три должны давать одно и то же, иначе адрес
    кнопки получится вида t.me/@SimbAD_alert_bot и никуда не ведёт.
    """
    v = (raw or "").strip().split("?")[0].rstrip("/")
    v = v.rsplit("/", 1)[-1].lstrip("@")
    return v or None


def bot_username() -> Optional[str]:
    """Юзернейм бота — то, что стоит после @ и работает в адресе t.me/<имя>.

    Источник истины — сам Telegram (getMe по токену), а НЕ переменная окружения:
    имя в .env вписывают руками, оно молча устаревает при смене бота, и ошибка
    вылезает не сообщением, а кнопкой, ведущей в несуществующий чат. Юзернейм —
    свойство токена, поэтому и спрашиваем его у владельца токена.

    Ответ кэшируется на процесс (ключ — токен, смена токена требует перезапуска и
    так). Сеть недоступна или бот не настроен — откатываемся на .env, привязку это
    не ломает: без имени просто не будет кнопки.
    """
    token = bot_token()
    env = _clean_name(os.getenv("TELEGRAM_BOT_NAME") or "")
    if not token:
        return env
    if token not in _USERNAME_CACHE:
        name = None
        try:
            r = httpx.get(API.format(token=token, method="getMe"), timeout=5)
            if r.status_code == 200:
                name = ((r.json() or {}).get("result") or {}).get("username") or None
        except Exception:
            name = None
        _USERNAME_CACHE[token] = name
    return _USERNAME_CACHE[token] or env


def link_url(code: str) -> Optional[str]:
    """Диплинк «открыть бота и отдать ему код».

    t.me/<бот>?start=<код> — Telegram сам подставляет «/start <код>» в кнопку
    «Начать», то есть вводить код руками не нужно вовсе. Код — hex в верхнем
    регистре, он укладывается в разрешённый payload (A-Z a-z 0-9 _ -).

    Кнопка не заменяет код на экране: если чат с ботом уже открывали, кнопки
    «Начать» в нём нет, и код отправляют сообщением.
    """
    name = bot_username()
    return f"https://t.me/{name}?start={code}" if name and code else None


def new_link_code() -> Tuple[str, datetime]:
    """Код привязки: короткий, одноразовый, живёт полчаса."""
    return secrets.token_hex(3).upper(), datetime.utcnow() + timedelta(minutes=LINK_CODE_TTL_MIN)


def send_message(chat_id: str, text: str, link: Optional[str] = None,
                 base_url: Optional[str] = None) -> None:
    """Отправить сообщение. Бросает исключение — вызывающий пишет причину в журнал.

    Ссылка добавляется отдельной строкой абсолютным адресом: в Telegram нет нашего
    origin, относительный путь вида /accounts/mp/12 там бесполезен.
    """
    token = bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
    body = text
    if link:
        domain = (base_url or os.getenv("DOMAIN") or "").strip()
        if domain and not domain.startswith("http"):
            domain = f"https://{domain}"
        if domain:
            body = f"{text}\n{domain.rstrip('/')}{link}"
    r = httpx.post(API.format(token=token, method="sendMessage"),
                   json={"chat_id": chat_id, "text": body,
                         "disable_web_page_preview": True},
                   timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram {r.status_code}: {r.text[:200]}")


def parse_start_command(update: dict) -> Tuple[Optional[str], Optional[str]]:
    """Из апдейта вебхука вытаскиваем (код привязки, chat_id).

    Апдейт приходит СНАРУЖИ и доверять ему нельзя: берём только два поля и только
    в ожидаемом формате `/start <код>`, всё остальное игнорируем.
    """
    msg = (update or {}).get("message") or (update or {}).get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = str(((msg.get("chat") or {}).get("id") or "")) or None
    if not chat_id or not text.startswith("/start"):
        return None, chat_id
    parts = text.split(maxsplit=1)
    code = parts[1].strip().upper() if len(parts) > 1 else None
    return (code or None), chat_id
