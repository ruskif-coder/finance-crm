"""Закреплённые и недавние экраны меню — личная настройка пользователя (навигация v3, хендофф 17.11.2026).

Таблица `user_nav_prefs` создаётся миграцией `2026-11-17_user_nav_prefs.sql`. Хранятся АДРЕСА экранов, а не ключи:
адрес — то, по чему меню находит экран в карте `nav.data.json` и куда ведёт кнопка; экран, пропавший из карты или
закрытый правом, фронт просто не покажет, хранить его здесь не вредно.
"""
import json

from fastapi import HTTPException
from sqlalchemy import text

MAX_PINS = 3          # README хендоффа §3: «Максимум три»
RECENT_LIMIT = 12     # README §3: «хранится 12»
MAX_LEN = 200
DEFAULT_PINNED = ["/finance/operations"]   # README §3: «По умолчанию закреплён „Финансы → Операции“»


def _internal(href):
    """Только адрес внутри приложения: `/…`, но не `//host` (протокол-относительный уводит на чужой сайт)."""
    return (isinstance(href, str) and 1 < len(href) <= MAX_LEN and href.startswith("/")
            and not href.startswith("//") and "\\" not in href)


def _clean(hrefs, limit, what):
    if not all(_internal(h) for h in hrefs):
        raise HTTPException(422, f"{what}: только адреса экранов приложения")
    seen = []
    for h in hrefs:
        if h not in seen:
            seen.append(h)
    return seen[:limit]


def read(db, user_id):
    row = db.execute(text("SELECT pinned, recent FROM user_nav_prefs WHERE user_id = :u"), {"u": user_id}).first()
    if not row:
        return {"pinned": list(DEFAULT_PINNED), "recent": []}
    return {"pinned": list(row.pinned or []), "recent": list(row.recent or [])}


def save(db, user_id, pinned, recent):
    if len(pinned) > MAX_PINS:
        raise HTTPException(422, f"Закрепить можно не больше {MAX_PINS} экранов")
    pinned = _clean(pinned, MAX_PINS, "Закреплённые")
    recent = _clean(recent, RECENT_LIMIT, "Недавние")
    db.execute(text("""
        INSERT INTO user_nav_prefs (user_id, pinned, recent, updated_at)
        VALUES (:u, CAST(:p AS jsonb), CAST(:r AS jsonb), now())
        ON CONFLICT (user_id) DO UPDATE SET pinned = EXCLUDED.pinned, recent = EXCLUDED.recent, updated_at = now()
    """), {"u": user_id, "p": json.dumps(pinned), "r": json.dumps(recent)})
    db.commit()
    return {"pinned": pinned, "recent": recent}
