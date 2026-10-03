# -*- coding: utf-8 -*-
"""Админ-кабинет DSP: статистика по сайтам для проверки «пропали из показов».

Статистика по сайтам есть только в админ-кабинете DSP, а не в партнёрском API, поэтому
адрес отдельный (`DSP_ADMIN_API_URL`). Доступ — тот же токен нашей DSP (владелец
30.09.2026), логин и пароль админки — запасной путь. Без адреса проверка честно говорит
«не настроено».

Вынесено из `traffic/site_monitor.py` 02.10.2026 (аудит интеграций): там был второй,
самописный клиент DSP, и ошибка уходила наружу с адресом и телом ответа. Ошибки здесь
чистятся тем же правилом, что у основного клиента (`client.safe_error`).
"""
import os
from datetime import date
from typing import Optional

import httpx

from app.dsp.client import _URL_RE, safe_error

ENV = ("DSP_ADMIN_API_URL", "DSP_ADMIN_LOGIN", "DSP_ADMIN_PASSWORD")
TOKEN_ENV = "DSP_ACCESS_TOKEN"
TIMEOUT = 60.0


class AdminError(RuntimeError):
    """Сбой админ-кабинета DSP; текст уже без адреса."""


def configured() -> bool:
    return bool(os.getenv("DSP_ADMIN_API_URL")) and bool(
        os.getenv(TOKEN_ENV) or (os.getenv("DSP_ADMIN_LOGIN") and os.getenv("DSP_ADMIN_PASSWORD")))


def _rpc(client: httpx.Client, url: str, method: str, params: dict, rid: int):
    try:
        r = client.post(url, json={"jsonrpc": "2.0", "method": method, "params": params, "id": rid})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise AdminError(f"{method}: {safe_error(e)}") from None
    if data.get("error"):
        raise AdminError(f"{method}: " + _URL_RE.sub("<адрес DSP>", str(data["error"]))[:300])
    return data.get("result")


def _login(c: httpx.Client, url: str) -> None:
    """Вход в админку. Наш партнёрский токен она НЕ принимает (замер 03.10.2026:
    «invalid token signature») — логин и пароль первыми, токен запасным."""
    login, password = os.getenv("DSP_ADMIN_LOGIN"), os.getenv("DSP_ADMIN_PASSWORD")
    if login and password:
        tok = (_rpc(c, url, "user.auth", {"login": login, "password": password}, 1)
               or {}).get("access_token")
    else:
        tok = os.getenv(TOKEN_ENV)
    if not tok:
        raise AdminError("DSP: в ответе на вход нет токена")
    c.headers["Authorization"] = f"Bearer {tok}"


def block_shows(day: date, block_ids, transport: Optional[httpx.BaseTransport] = None) -> dict:
    """Показы блоков за день: {id блока: (показы, клики)}. Блок без показов в ответ не
    приходит — значит ноль (админка отдаёт только строки с данными; замер 03.10.2026).

    Группировка только по блоку (`main_group: placement`): по кампании админка не делит,
    фильтр `campaign` молча игнорирует."""
    ids = sorted({str(b) for b in block_ids if b})
    if not ids:
        return {}
    url = os.getenv("DSP_ADMIN_API_URL")
    with httpx.Client(timeout=TIMEOUT, transport=transport) as c:
        _login(c, url)
        items = _rpc(c, url, "platform.getStatistics", {"filter": {
            "date_from": day.isoformat(), "date_to": day.isoformat(),
            "placement": ids, "main_group": ["placement"]}}, 2) or []
    out = {b: (0, 0) for b in ids}
    for it in items:
        b = str(it.get("placement") or "")
        if b in out:
            try:
                out[b] = (int(it.get("shows") or 0), int(it.get("clicks") or 0))
            except (TypeError, ValueError):
                pass
    return out


def sites_with_shows(day: date, transport: Optional[httpx.BaseTransport] = None) -> set:
    """Сайты, у которых за день были показы."""
    url = os.getenv("DSP_ADMIN_API_URL")
    with httpx.Client(timeout=TIMEOUT, transport=transport) as c:
        _login(c, url)
        items = _rpc(c, url, "platform.getStatistics", {"filter": {
            "date_from": day.isoformat(), "date_to": day.isoformat(),
            "main_group": ["site"]}}, 2) or []
    out = set()
    for it in items:
        try:
            shows = int(it.get("shows") or 0)
        except (TypeError, ValueError):
            shows = 0
        if it.get("site") and shows > 0:
            out.add(it["site"])
    return out
