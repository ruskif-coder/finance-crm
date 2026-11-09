# -*- coding: utf-8 -*-
"""Чтение очереди модерации SSP. ТОЛЬКО чтение: одобрять и отклонять у SSP пока не будем (владелец 07.11.2026).

Модерация живёт в том же админ-кабинете и под тем же входом, что `app/dsp/admin.py` — отдельных ключей нет.
Параметры списка передаются внутри `filter` (замер 07.11: без него кабинет отвечает не-JSON).
Запись `getList`: uuid, erid, crid, status (0 ждёт, 1 одобрено, 2 отклонено), priority, reason, comment,
scores, updated_at, moderated_at, moderated_by, preview_url, publishers[int].
"""
import os
from typing import List

import httpx

from app.dsp import admin

PAGE = 1000
TIMEOUT = 30.0


class SspError(RuntimeError):
    """Сбой чтения у SSP; текст без адреса кабинета."""


def configured() -> bool:
    return admin.configured()


def _client() -> httpx.Client:
    return httpx.Client(timeout=admin.TIMEOUT)


def fetch_list() -> List[dict]:
    """Все заявки модерации, постранично."""
    url = os.getenv("DSP_ADMIN_API_URL")
    out: List[dict] = []
    try:
        with _client() as c:
            admin._login(c, url)
            while True:
                res = admin._rpc(c, url, "creativeModeration.getList",
                                 {"filter": {"limit": PAGE, "offset": len(out)}}, 2) or {}
                items = res.get("items") or []
                out.extend(items)
                if not items or len(out) >= int(res.get("total") or 0):
                    return out
    except admin.AdminError as e:
        raise SspError(str(e)) from None


def fetch_reasons() -> List[dict]:
    """Дерево причин отказа: `{id, number, level, title, canSelected}`."""
    url = os.getenv("DSP_ADMIN_API_URL")
    try:
        with _client() as c:
            admin._login(c, url)
            return admin._rpc(c, url, "creativeModeration.getRefusalReasons", {}, 3) or []
    except admin.AdminError as e:
        raise SspError(str(e)) from None


def fetch_markup(preview_url: str) -> str:
    """Разметка креатива по ссылке предпросмотра (без авторизации)."""
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(preview_url)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        raise SspError(f"разметка не получена: {type(e).__name__}") from None
