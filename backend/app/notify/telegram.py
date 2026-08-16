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
