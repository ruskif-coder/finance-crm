"""Личные настройки вида таблиц — у пользователя на сервере, а не в браузере (владелец 19.11.2026).

Таблица `user_ui_prefs` создаётся миграцией `2026-11-19_user_ui_prefs.sql`. Ключ — что настраивается; принимаются
только ключи из `KEYS`, и у каждого — своя проверка формы: таблица не должна стать складом произвольного JSON.
"""
import json

from fastapi import HTTPException
from sqlalchemy import text

# Колонки таблицы площадок в расхлопе дашборда трафика, которые человек может скрыть и переставить: всё между
# «Площадкой» (закреплена слева) и «Статусом». Ключи — те же, что `COLS` в frontend/components/traffic/v2/SiteRow.jsx.
SITES_COLUMNS = ("cr", "weight", "share", "plan", "fact", "clk", "ctr", "exec", "under", "wr", "pace")


def _columns(allowed):
    def check(v):
        if not isinstance(v, dict) or set(v) != {"order", "hidden"}:
            raise HTTPException(422, "Настройка колонок: нужны order и hidden")
        for part in ("order", "hidden"):
            xs = v[part]
            if not isinstance(xs, list) or not all(isinstance(x, str) for x in xs):
                raise HTTPException(422, f"Настройка колонок: {part} — список названий")
            if len(set(xs)) != len(xs):
                raise HTTPException(422, f"Настройка колонок: в {part} колонка дважды")
            if set(xs) - set(allowed):
                raise HTTPException(422, f"Настройка колонок: таких колонок нет — {', '.join(sorted(set(xs) - set(allowed)))}")
        return {"order": list(v["order"]), "hidden": list(v["hidden"])}
    return check


KEYS = {"traffic.sites.columns": _columns(SITES_COLUMNS)}


def _known(key):
    if key not in KEYS:
        raise HTTPException(404, "Такой настройки нет")


def read(db, user_id, key):
    _known(key)
    return db.execute(text("SELECT value FROM user_ui_prefs WHERE user_id = :u AND key = :k"),
                      {"u": user_id, "k": key}).scalar()


def save(db, user_id, key, value):
    _known(key)
    value = KEYS[key](value)
    db.execute(text("""
        INSERT INTO user_ui_prefs (user_id, key, value, updated_at) VALUES (:u, :k, CAST(:v AS jsonb), now())
        ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
    """), {"u": user_id, "k": key, "v": json.dumps(value)})
    db.commit()
    return value
