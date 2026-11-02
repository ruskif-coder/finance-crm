"""Техобслуживание кабинета паблишеров (владелец 02.11.2026).

Режим объявляет ядро (`backend/app/maintenance.py`, кнопка на экране «Статус») и хранит в `company_settings`. Кабинет
под своей ролью этой таблицы не видит и читает витрину `pub.maintenance_v1`: время начала и что закрыто. Кабинет
закрывается, только если в области есть «cabinet» — закрытый портал площадку не касается.

Как у ядра: за 10 минут до начала — полоса с обратным отсчётом, после — закрыто всё, кроме ручки состояния (иначе
экран не скажет, почему закрыто) и проверки живости. Вход закрыт тоже: в кабинете нет администратора, которого надо
пускать снять режим, — снимают его в ядре. Испорченное время выключает режим, а не запирает площадки.

Своя пара функций, а не импорт из ядра: кабинет — отдельный процесс и `app.*` ядра не импортирует по построению.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db import plain_session

TITLE = "Кабинет на техобслуживании"
NOTE = ("Скоро вернёмся. Ваши ответы, отправленные до начала, сохранены. Кампании продолжают крутиться в обычном "
        "режиме — техобслуживание касается только кабинета.")
BAR = "Если вы отвечаете по креативу или сверке — отправьте ответ сейчас."

OPEN_PATHS = ("/api/maintenance", "/api/health")


def cabinet_state(starts_at: Optional[str], scope: Optional[str], now: datetime) -> dict:
    """Режим КАБИНЕТА по строке витрины. Чистая функция — её зовёт прибор."""
    off = {"mode": "off", "seconds_left": None}
    if not starts_at or "cabinet" not in (scope or "").split(","):
        return off
    try:
        start = datetime.fromisoformat(starts_at)
    except ValueError:
        return off
    left = int((start - now).total_seconds())
    return {"mode": "announced" if left > 0 else "active", "seconds_left": max(0, left),
            "title": TITLE, "note": NOTE, "bar": BAR}


def current() -> dict:
    """Режим сейчас. Недоступная база — не повод закрывать кабинет: заглушка соврала бы о причине."""
    try:
        db = plain_session()
        try:
            row = db.execute(text("SELECT starts_at, scope FROM pub.maintenance_v1")).first()
        finally:
            db.close()
    except Exception:                                   # noqa: BLE001
        return {"mode": "off", "seconds_left": None}
    return cabinet_state(row.starts_at if row else None, row.scope if row else None, datetime.utcnow())


def blocks(path: str, method: str, mode: str) -> bool:
    """Закрыт ли запрос. Только после наступления; открыты лишь состояние и проверка живости."""
    if mode != "active" or not path.startswith("/api/"):
        return False
    return not any(path == p or path.startswith(p + "/") for p in OPEN_PATHS)
