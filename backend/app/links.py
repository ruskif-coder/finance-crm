# -*- coding: utf-8 -*-
"""Единственная проверка схемы ссылки на документ.

Любая ссылка, приехавшая из данных, рано или поздно рендерится на фронте как
`<a href={...}>`. Схема `javascript:` в таком атрибуте исполняет код в сессии
того, кто по ней кликнул, — а токен лежит в localStorage, то есть это захват
аккаунта, а не косметика. Поэтому список схем закрытый, а не чёрный.

До 2026-08-23 эта функция существовала в двух почти одинаковых копиях —
в `contracts.py` и в `operations.py`, — а третий потребитель (реестр документов
Диадока) не проверял ничего.
"""
import re
from typing import Optional

from fastapi import HTTPException

ALLOWED_LINK_SCHEMES = ("http://", "https://")


def validate_link(url, raise_on_bad: bool = True) -> Optional[str]:
    """http/https → очищенная ссылка; иначе 400 либо None.

    `raise_on_bad=False` — для импортов из файлов: одна битая строка не должна
    ронять весь импорт, небезопасная ссылка просто отбрасывается.
    """
    if url is None:
        return None
    u = str(url).strip()
    if not u:
        return None
    if not any(u.lower().startswith(s) for s in ALLOWED_LINK_SCHEMES):
        if raise_on_bad:
            raise HTTPException(
                status_code=400,
                detail="Ссылка на документ должна начинаться с http:// или https://",
            )
        return None
    return u


# Ссылки на КАНАЛЫ СВЯЗИ (чат площадки, мессенджер, макет) — те же http/https плюс `tg:`:
# телеграм отдаёт такие ссылки сам, и отказывать в них значило бы толкать людей писать
# в поле что попало. Закрытый список по той же причине, что выше (аудит 23.09.2026, 7.M1:
# эти поля сохранялись вовсе без проверки и рисуются кликабельными — в том числе в
# кабинете самой площадки).
ALLOWED_CHAT_SCHEMES = ALLOWED_LINK_SCHEMES + ("tg://",)


# Схема — «буквы:» в самом начале. Опасна только ЧУЖАЯ схема (`javascript:`, `data:`,
# `vbscript:`, `file:`); текст без схемы безопасен — экран сам не делает из него
# исполняемую ссылку (`lib/safeHref`), а запрет его ронял сохранение карточки: форма
# уходит целиком, и `t.me/чат` или `@чат`, давно лежащие в поле, давали 422 (ревью
# 23.09.2026).
_SCHEME = re.compile(r"^\s*([a-z][a-z0-9+.\-]*):", re.IGNORECASE)


def safe_url(url) -> Optional[str]:
    """Ссылка на канал связи: пусто → None; своя схема или её отсутствие → строка как
    есть; чужая схема → ValueError (pydantic превращает его в 422 с именем поля)."""
    if url is None:
        return None
    u = str(url).strip()
    if not u:
        return None
    m = _SCHEME.match(u)
    if m and not u.lower().startswith(ALLOWED_CHAT_SCHEMES):
        raise ValueError(f"Схема «{m.group(1)}:» в ссылке запрещена — "
                         f"только http://, https:// или tg://")
    return u
