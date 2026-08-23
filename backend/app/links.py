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
