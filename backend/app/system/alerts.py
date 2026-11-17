"""Оповещения о смене состояния проверок (хендофф «Статус системы», 16.11.2026).

Шлём при СМЕНЕ, а не при каждом прогоне — переходы приносит `history.record`:
  отказ                    — сразу, при переходе в `bad`;
  вернулось в норму        — сразу, при выходе из `bad`, с временем простоя;
  не настроено / истекает  — одной сводкой раз в сутки, в 09:00 МСК (`daily_warn`).
Получатели — администраторы (реестр уведомлений), каналы — переключатели поповера «Оповещения»: в интерфейсе
сообщение лежит всегда, Телеграм и почта — по выбору. «вкл» на кнопке — хотя бы одно событие и хотя бы один канал.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import timez

log = logging.getLogger("finance.status")

KEY = "status_alerts"
KEY_DIGEST_DAY = "status_alerts_digest_day"
DEFAULT = {"bad": True, "warn": True, "ok": True, "tg": True, "mail": False}
DIGEST_HOUR_MSK = 9
LINK = "/settings/system"


def _get(db: Session, key: str) -> Optional[str]:
    return db.execute(text("SELECT value FROM company_settings WHERE key = :k"), {"k": key}).scalar()


def _put(db: Session, key: str, value: str) -> None:
    db.execute(text("""INSERT INTO company_settings (key, value) VALUES (:k, :v)
                       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"""), {"k": key, "v": value})


def config(db: Session) -> dict:
    try:
        saved = json.loads(_get(db, KEY) or "{}")
    except (TypeError, ValueError):
        saved = {}
    return {k: bool(saved.get(k, v)) for k, v in DEFAULT.items()}


def save(db: Session, data: dict) -> dict:
    cfg = {k: bool(data.get(k, v)) for k, v in config(db).items()}
    _put(db, KEY, json.dumps(cfg))
    db.commit()
    return cfg


def is_on(cfg: dict) -> bool:
    return (cfg["bad"] or cfg["warn"] or cfg["ok"]) and (cfg["tg"] or cfg["mail"])


def channels(cfg: dict) -> set:
    return {c for c in ("tg", "mail") if cfg.get(c)}


def plan(transitions: List[dict], cfg: dict) -> List[Tuple[str, dict]]:
    """Какие события породить по переходам: [(ключ события, переход)]. Без каналов — ничего."""
    if not (cfg.get("tg") or cfg.get("mail")):
        return []
    out = []
    for t in transitions:
        if t["to"] == "bad" and t.get("from") != "bad" and cfg.get("bad"):
            out.append(("system_check_failed", t))
        elif t.get("from") == "bad" and t["to"] in ("ok", "idle") and cfg.get("ok"):
            out.append(("system_check_recovered", t))
    return out


def _downtime(since: Optional[datetime], now: datetime) -> str:
    if since is None:
        return ""
    mins = int((now - since).total_seconds() // 60)
    return f"{mins // 60} ч {mins % 60:02d} мин" if mins >= 60 else f"{mins} мин"


def send(db: Session, transitions: List[dict], now: Optional[datetime] = None) -> int:
    """Разослать по переходам. Сбой рассылки не роняет прогон — пишется в лог."""
    from app.notify import bus
    now = now or datetime.utcnow()
    cfg = config(db)
    n = 0
    for ev, t in plan(transitions, cfg):
        c = t["check"]
        if ev == "system_check_failed":
            title = f"Отказ: {c.get('title')}"
            body = (c.get("consequence") or c.get("note") or c.get("value") or "") + \
                   (f" · {c.get('value')}" if c.get("consequence") and c.get("value") else "")
        else:
            title = f"Вернулось в норму: {c.get('title')}"
            body = f"Простой {_downtime(t.get('down_since'), now)}. Сейчас: {c.get('value') or 'в норме'}"
        try:
            bus.emit(db, ev, title=title, body=body, link=LINK, tone="bad" if ev == "system_check_failed" else "ok",
                     only_channels=channels(cfg))
            n += 1
        except Exception:  # noqa: BLE001 — оповещение справка, состояние уже записано
            log.exception("оповещение %s по %s не ушло", ev, t["key"])
    db.commit()
    return n


def daily_warn(db: Session, checks: List[dict], now: Optional[datetime] = None) -> bool:
    """Сводка «не настроено / истекает» — раз в сутки, в первый прогон после 09:00 МСК. True — ушла."""
    from app.notify import bus
    now = now or datetime.utcnow()
    msk = timez.to_msk(now)
    cfg = config(db)
    if msk.hour < DIGEST_HOUR_MSK or not cfg["warn"] or not channels(cfg):
        return False
    today = msk.date().isoformat()
    if _get(db, KEY_DIGEST_DAY) == today:
        return False
    _put(db, KEY_DIGEST_DAY, today)
    warn = [c for c in checks if c.get("tone") == "warn"]
    if warn:
        lines = [f"{c.get('title')}: {c.get('value') or ''}" for c in warn]
        try:
            bus.emit(db, "system_check_warn_digest", title=f"Требуют настройки: {len(warn)}",
                     body="\n".join(lines), link=LINK, tone="warn", only_channels=channels(cfg))
        except Exception:  # noqa: BLE001
            log.exception("сводка предупреждений не ушла")
    db.commit()
    return bool(warn)
