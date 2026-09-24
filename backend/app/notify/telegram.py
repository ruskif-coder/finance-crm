"""Канал доставки Telegram.

Библиотек для бота не тянем — это два HTTP-запроса через httpx, который уже есть.

ДВА КОНТУРА, один протокол: бот сотрудников и бот кабинета площадок. Контур передаётся
параметром `contour` (STAFF/PUB), от него зависят токен, имя и адрес привязки.

Конфигурация: TELEGRAM_BOT_TOKEN / TELEGRAM_PUB_BOT_TOKEN в .env (не коммитится). Без токена канал считается
ненастроенным: сообщения не теряются, а ложатся в журнал отправок статусом queued —
уйдут после настройки командой flush, а не пропадут молча.

Привязка: пользователь жмёт «Привязать» → получает код → отправляет боту `/start <код>`.
Бот присылает апдейт на вебхук, мы находим код и запоминаем chat_id. Пароли и токены
пользователя при этом нигде не участвуют.
"""
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import httpx

API = "https://api.telegram.org/bot{token}/{method}"
LINK_CODE_TTL_MIN = 30

# СКОЛЬКО РАЗ ПРОБОВАТЬ ОДИН ЗАПРОС — одно число на весь контур Телеграма, и опрос
# (`app/notify/tg_poll.py`) берёт его отсюда же. Замер 21.09.2026 на проде: из восьми
# адресов api.telegram.org с сервера жив РОВНО ОДИН (149.154.167.220, он закреплён в
# прод-compose через `extra_hosts`), и отвечает он примерно в трёх случаях из четырёх —
# 9 удач из 12. Двух попыток мало: одна неудача на шестнадцать отправок. Трёх хватает:
# 6 операций из 6. Второе такое же число в другом файле разошлось бы с этим молча.
ATTEMPTS = 3

# ПРОКСИ ДО ТЕЛЕГРАМА — одна точка на весь контур: отправка, getMe, опрос и проверка
# состояния ходят через него же.
#
# Зачем: с прода жив ровно один адрес api.telegram.org из восьми, и отвечает он примерно
# в трёх случаях из четырёх (замер 21.09.2026). Прокси на машине за пределами этой сети
# снимает и рваность, и зависимость от закреплённого вручную адреса.
#
# ТОЛЬКО CONNECT или SOCKS5. При них шифрование идёт до самого Телеграма, и прокси видит
# лишь адрес назначения — токен ему недоступен. Прокси, разворачивающий TLS, использовать
# нельзя: он увидит токен бота целиком.
#
# Пусто — ходим напрямую, как раньше. Это рабочее состояние, а не поломка.
ENV_PROXY = "TELEGRAM_PROXY_URL"


def proxy() -> Optional[str]:
    """Адрес прокси или None. Отдельной функцией, чтобы точек чтения было не четыре."""
    return (os.getenv(ENV_PROXY) or "").strip() or None


# Прокси передаётся ПАРАМЕТРОМ в те же вызовы, что были, а не через свой клиент:
# `httpx.post/get` умеют `proxy=` начиная с 0.26. Свой клиент сместил бы шов, за который
# держатся три прибора (`test_tg_webhook_async`, `test_notify`), — а поведение при этом
# осталось бы прежним. Ломать приборы ради стиля нельзя.

# ДВА БОТА, А НЕ ОДИН (владелец 15.09.2026). Внутренний пишет сотрудникам, бот кабинета —
# площадкам. Разделение не техническое: площадка видит бота подрядчика, а не наш
# внутренний алёрт-бот, и обработчик `/start` не гадает, чей перед ним код — у каждого
# контура свой вебхук и своя таблица привязок.
#
# Контур — ПАРАМЕТР, а не копия модуля: протокол Телеграма один, и вторая копия этих
# функций разошлась бы с первой на первой же правке (повтор при обрыве живёт здесь).
STAFF, PUB = "staff", "pub"

# Имена переменных — ОТДЕЛЬНЫМИ КОНСТАНТАМИ, а не словарём `{контур: имя}`. Словарь здесь
# был и выглядел аккуратнее, но прибор `tests/test_env_passthrough` разбирает код деревом
# и умеет разворачивать константу модуля, а не выбор из словаря по ключу: под словарём
# исчезли из виду разом и новые переменные, и две старых, живших тут год. Прибор ловит
# ровно ту тишину, ради которой заведён, — «в .env значение есть, до процесса не дошло»,
# — и прятаться от него ради красоты нельзя.
ENV_TOKEN_STAFF = "TELEGRAM_BOT_TOKEN"
ENV_TOKEN_PUB = "TELEGRAM_PUB_BOT_TOKEN"
ENV_NAME_STAFF = "TELEGRAM_BOT_NAME"
ENV_NAME_PUB = "TELEGRAM_PUB_BOT_NAME"


def token_var(contour: str = STAFF) -> str:
    """Имя переменной окружения — для сообщения об ошибке: «не задан TELEGRAM_...»
    полезнее, чем «бот не настроен»."""
    return ENV_TOKEN_PUB if contour == PUB else ENV_TOKEN_STAFF


def bot_token(contour: str = STAFF) -> Optional[str]:
    raw = os.getenv(ENV_TOKEN_PUB) if contour == PUB else os.getenv(ENV_TOKEN_STAFF)
    return (raw or "").strip() or None


def configured(contour: str = STAFF) -> bool:
    return bot_token(contour) is not None


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


def bot_username(contour: str = STAFF) -> Optional[str]:
    """Юзернейм бота — то, что стоит после @ и работает в адресе t.me/<имя>.

    Источник истины — сам Telegram (getMe по токену), а НЕ переменная окружения:
    имя в .env вписывают руками, оно молча устаревает при смене бота, и ошибка
    вылезает не сообщением, а кнопкой, ведущей в несуществующий чат. Юзернейм —
    свойство токена, поэтому и спрашиваем его у владельца токена.

    Ответ кэшируется на процесс (ключ — токен, смена токена требует перезапуска и
    так). Сеть недоступна или бот не настроен — откатываемся на .env, привязку это
    не ломает: без имени просто не будет кнопки.
    """
    token = bot_token(contour)
    env = _clean_name((os.getenv(ENV_NAME_PUB) if contour == PUB
                       else os.getenv(ENV_NAME_STAFF)) or "")
    if not token:
        return env
    if token not in _USERNAME_CACHE:
        name = None
        try:
            r = httpx.get(API.format(token=token, method="getMe"), timeout=5,
                          proxy=proxy())
            if r.status_code == 200:
                name = ((r.json() or {}).get("result") or {}).get("username") or None
        except Exception:
            name = None
        _USERNAME_CACHE[token] = name
    return _USERNAME_CACHE[token] or env


def link_url(code: str, contour: str = STAFF) -> Optional[str]:
    """Диплинк «открыть бота и отдать ему код».

    t.me/<бот>?start=<код> — Telegram сам подставляет «/start <код>» в кнопку
    «Начать», то есть вводить код руками не нужно вовсе. Код — hex в верхнем
    регистре, он укладывается в разрешённый payload (A-Z a-z 0-9 _ -).

    Кнопка не заменяет код на экране: если чат с ботом уже открывали, кнопки
    «Начать» в нём нет, и код отправляют сообщением.
    """
    name = bot_username(contour)
    return f"https://t.me/{name}?start={code}" if name and code else None


# Код привязки — три байта hex, то есть шесть знаков 0-9A-F. Формат записан здесь один
# раз: по нему и выдаётся код, и узнаётся присланный голышом.
_CODE_RE = re.compile(r"[0-9A-Fa-f]{6}")


def new_link_code() -> Tuple[str, datetime]:
    """Код привязки: короткий, одноразовый, живёт полчаса."""
    return secrets.token_hex(3).upper(), datetime.utcnow() + timedelta(minutes=LINK_CODE_TTL_MIN)


def send_message(chat_id: str, text: str, link: Optional[str] = None,
                 base_url: Optional[str] = None, contour: str = STAFF) -> None:
    """Отправить сообщение. Бросает исключение — вызывающий пишет причину в журнал.

    Ссылка добавляется отдельной строкой абсолютным адресом: в Telegram нет нашего
    origin, относительный путь вида /accounts/mp/12 там бесполезен.
    """
    token = bot_token(contour)
    if not token:
        raise RuntimeError(f"{token_var(contour)} не задан")
    body = text
    if link:
        # Площадке — адрес её кабинета, а не внутренней системы (аудит 23.09.2026, 5.H2).
        if contour == PUB and not base_url:
            from app.mail.render import cabinet_url
            base_url = cabinet_url("/")
        domain = (base_url or os.getenv("DOMAIN") or "").strip()
        if domain and not domain.startswith("http"):
            domain = f"https://{domain}"
        if domain:
            body = f"{text}\n{domain.rstrip('/')}{link}"
    # ОДНА ПОВТОРНАЯ ПОПЫТКА при обрыве соединения (08.09.2026).
    #
    # Связь с Телеграмом у нас рваная по независящей от кода причине: адрес, который
    # отдаёт DNS, с сервера недостижим вовсе, рабочий закреплён через `extra_hosts`, и
    # он сам отвечает не всегда — замер показал 5 успехов из 6. Повтор снижает вероятность
    # неудачи примерно с одной шестой до одной тридцать шестой.
    #
    # Повторяем ТОЛЬКО обрыв соединения. Ответ Телеграма с кодом ошибки не повторяем: 403
    # («бот не запущен пользователем») и 400 («чат не найден») от повтора не изменятся, а
    # 429 требует выдержать паузу, которую Телеграм называет сам, — это другой разговор.
    # Число попыток — общая константа ATTEMPTS, см. её обоснование в шапке модуля.
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            r = httpx.post(API.format(token=token, method="sendMessage"),
                           json={"chat_id": chat_id, "text": body,
                                 "disable_web_page_preview": True},
                           timeout=10, proxy=proxy())
            break
        except httpx.TransportError as e:      # таймаут, обрыв, отказ в соединении
            last = e
            if attempt == ATTEMPTS:
                raise RuntimeError(f"Telegram недоступен: {type(e).__name__}") from last
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
    if not chat_id or not text:
        return None, chat_id
    # ГОЛЫЙ КОД ТОЖЕ ПРИНИМАЕМ. Инструкция говорит «отправьте код боту», и человек
    # отправляет именно код — без слова `/start`, которого он в глаза не видел. До
    # 18.09.2026 такое сообщение молча игнорировалось, и со стороны площадки это
    # выглядело как «бот не подключается»: она пишет, в ответ тишина.
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else None
    else:
        # Только одиночное слово нужной длины: любой текст кодом считать нельзя, иначе
        # чужая фраза случайно совпадёт с чьим-то кодом.
        code = text if (len(text.split()) == 1 and _CODE_RE.fullmatch(text)) else None
    return ((code or "").upper() or None), chat_id
