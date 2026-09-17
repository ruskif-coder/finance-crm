"""Техобслуживание: объявление, наступление, снятие.

СОСТОЯНИЕ ЖИВЁТ В БАЗЕ, а не в памяти процесса. Иначе первый же перезапуск контейнера
снял бы режим молча — а мы бы считали, что он включён, и спокойно правили прод при живых
пользователях. Три ключа в `company_settings`, миграция не нужна.

ТРИ СОСТОЯНИЯ, и они не одно и то же:

    объявлено   до `maintenance_from` — все видят полосу «через N минут», работа идёт;
    началось    после — вход закрыт, запись закрыта, кто внутри, видит заглушку;
    снято       ключей нет.

АДМИН ПРОХОДИТ ВСЕГДА. Иначе включивший обслуживание закроет вход себе же и снимет режим
только из консоли базы — то есть ровно тогда, когда это сложнее всего.

СНИМАЕТСЯ РУКАМИ. Автоснятие по таймеру вернуло бы людей в систему, которую мы ещё не
починили: «время вышло» и «работа закончена» — разные утверждения.

Крон режим НЕ останавливает (решение 17.09.2026): пропущенный час досылки писем
восстанавливается сам, пропущенный съём статистики — нет. То есть письма во время
обслуживания уходить будут, и это осознанно.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

KEY_FROM = "maintenance_from"        # ISO-время наступления
KEY_NOTE = "maintenance_note"        # текст для людей
KEY_BY = "maintenance_by"            # кто объявил — для журнала и для экрана

# Предупреждение фиксированное (решение владельца 17.09.2026). Десять минут — не
# «круглое число»: это верхняя граница того, что человек готов ждать, не бросив работу,
# и нижняя того, за что успевает дописать начатое.
LEAD_MINUTES = 10

NOTE_DEFAULT = ("Портал прервётся на техобслуживание. Просим сохранить вашу работу — "
                "после начала сохранение будет недоступно.")
STUB_TITLE = "Мы на техобслуживании"
STUB_NOTE = ("Скоро вернёмся. Работа сохранена — как только обслуживание закончится, "
             "страница откроется обычным образом.")

# Что остаётся доступным даже в разгар обслуживания. Вход — обязательно: иначе админ не
# войдёт снять режим. Состояние — обязательно: иначе экран не сможет объяснить, почему
# всё закрыто, и покажет пустую ошибку.
# `/api/health` и `/` в списке НЕТ намеренно: такого маршрута в проекте не существует,
# а корень до прослойки не доходит вовсе — она смотрит только пути на `/api/`. Держать
# в списке защиту несуществующего адреса значит однажды поверить, что она что-то делает.
OPEN_PATHS = ("/api/auth/login", "/api/maintenance")
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _get(db: Session, key: str) -> Optional[str]:
    v = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                   {"k": key}).scalar()
    return (v or "").strip() or None


def _set(db: Session, key: str, value: Optional[str]) -> None:
    """Снятие — это ПУСТОЕ ЗНАЧЕНИЕ, а не удаление строки.

    Так требует общее правило проекта (разрушающего SQL в `app/` нет, прибор
    `test_startup_ddl`), и так же честнее по смыслу: строка остаётся, и по ней видно,
    что режим здесь когда-то включали. `_get` пустое значение и так читает как «нет».
    """
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": key, "v": value or ""})


def state(db: Session) -> dict:
    """Текущее состояние режима. Одна точка чтения на оба контура и на прослойку."""
    raw = _get(db, KEY_FROM)
    if not raw:
        return {"mode": "off", "from": None, "note": None, "by": None,
                "seconds_left": None}
    try:
        start = datetime.fromisoformat(raw)
    except ValueError:
        # Испорченное значение — НЕ повод закрыть систему: режим выключаем и говорим
        # об этом в логе. Обратное решение запирает людей из-за опечатки в настройке.
        return {"mode": "off", "from": None, "note": None, "by": None,
                "seconds_left": None, "broken": raw}
    now = datetime.utcnow()
    left = int((start - now).total_seconds())
    return {
        "mode": "announced" if left > 0 else "active",
        "from": start.isoformat(),
        "note": _get(db, KEY_NOTE) or NOTE_DEFAULT,
        "by": _get(db, KEY_BY),
        "seconds_left": max(0, left),
        "stub_title": STUB_TITLE, "stub_note": STUB_NOTE,
    }


def announce(db: Session, *, by: str, note: Optional[str] = None) -> dict:
    """Объявить обслуживание через `LEAD_MINUTES` минут."""
    start = datetime.utcnow() + timedelta(minutes=LEAD_MINUTES)
    _set(db, KEY_FROM, start.isoformat())
    _set(db, KEY_NOTE, (note or "").strip() or NOTE_DEFAULT)
    _set(db, KEY_BY, by)
    db.commit()
    return state(db)


def cancel(db: Session) -> dict:
    """Снять режим — и отменой до наступления, и завершением после. Действие одно:
    разница только в том, наступило оно или нет, а состояние после обоих одинаковое."""
    for k in (KEY_FROM, KEY_NOTE, KEY_BY):
        _set(db, k, "")
    db.commit()
    return state(db)


def blocks(path: str, method: str, *, is_admin: bool, mode: str) -> bool:
    """Закрыт ли этот запрос. Чистая функция — её же зовёт прибор.

    Закрываем ТОЛЬКО после наступления: до него работа идёт как обычно (решение
    владельца 17.09.2026). Следствие названо вслух и принято: человек, начавший
    заполнять форму до начала, получит отказ при сохранении.
    """
    if mode != "active" or is_admin:
        return False
    # Совпадение ТОЧНОЕ либо по границе сегмента. Первая редакция проверяла
    # `startswith(p.rstrip("/") + "/")`, а в списке есть корень «/» — после обрезки он
    # превращался в пустую строку, и открытым оказывался КАЖДЫЙ адрес. Режим при этом
    # включался, показывал заглушку и не закрывал ничего: худший вид поломки — тот,
    # который выглядит как работа.
    for p in OPEN_PATHS:
        if path == p or (p != "/" and path.startswith(p.rstrip("/") + "/")):
            return False
    return method in WRITE_METHODS or method == "GET"
