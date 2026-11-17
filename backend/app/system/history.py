"""Состояние проверок во времени: «с какого момента» и история за 14 дней (хендофф «Статус системы», 16.11.2026).

Пишет фоновый прогон (`app.system.watch`), экран только читает. Серия — непрерывный отрезок ОДНОГО тона: первый
прогон с другим тоном начинает её заново, поэтому «с 14.11 · 3 дня» значит «отказывает без перерыва с 14.11».

`record` возвращает ПЕРЕХОДЫ — смены тона. Оповещения строятся только по ним (`alerts.plan`), а не по каждому прогону:
три ночи подряд упавшее задание — одно сообщение об отказе и одно о восстановлении.

Время в базе — наивное UTC, как во всей системе; подписи — по Москве.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import timez

DAYS = 14
RANK = {"ok": 0, "idle": 1, "warn": 2, "bad": 3}


def _msk(dt: datetime) -> datetime:
    return timez.to_msk(dt)


def _failure_text(c: dict, now: datetime) -> str:
    what = c.get("consequence") or c.get("note") or c.get("value") or c.get("tone")
    return f"{_msk(now).strftime('%d.%m в %H:%M')} · {what}"


def record(db: Session, checks: Iterable[dict], now: Optional[datetime] = None) -> List[dict]:
    """Записать прогон. Возвращает переходы [{key, title, from, to, down_since, check}] — `from` пуст у новой проверки."""
    now = now or datetime.utcnow()
    checks = [c for c in checks if c.get("key")]
    have = {r[0]: (r[1], r[2]) for r in db.execute(text(
        "SELECT check_key, tone, since FROM system_check_state WHERE check_key = ANY(:k)"),
        {"k": [c["key"] for c in checks]}).all()}
    day = _msk(now).date()
    out = []
    for c in checks:
        key, tone = c["key"], c["tone"]
        prev = have.get(key)
        # Новая проверка — переход, только если она сразу в отказе: «появилась и в норме» сообщать не о чем
        changed = (prev[0] != tone) if prev else tone == "bad"
        failure = _failure_text(c, now) if tone in ("bad", "warn") else None
        db.execute(text("""
            INSERT INTO system_check_state (check_key, tone, since, last_checked_at, last, last_failure, last_failure_at)
            VALUES (:k, :t, :now, :now, CAST(:last AS jsonb), :f, CASE WHEN :f IS NULL THEN NULL ELSE CAST(:now AS timestamp) END)
            ON CONFLICT (check_key) DO UPDATE SET
                tone = EXCLUDED.tone,
                since = CASE WHEN system_check_state.tone = EXCLUDED.tone THEN system_check_state.since ELSE EXCLUDED.since END,
                last_checked_at = EXCLUDED.last_checked_at,
                last = EXCLUDED.last,
                last_failure = coalesce(EXCLUDED.last_failure, system_check_state.last_failure),
                last_failure_at = coalesce(EXCLUDED.last_failure_at, system_check_state.last_failure_at)"""),
            {"k": key, "t": tone, "now": now, "last": json.dumps(c, ensure_ascii=False, default=str), "f": failure})
        db.execute(text("""
            INSERT INTO system_check_day (check_key, day, tone) VALUES (:k, :d, :t)
            ON CONFLICT (check_key, day) DO UPDATE SET tone = CASE
                WHEN (CASE EXCLUDED.tone WHEN 'bad' THEN 3 WHEN 'warn' THEN 2 WHEN 'idle' THEN 1 ELSE 0 END)
                   > (CASE system_check_day.tone WHEN 'bad' THEN 3 WHEN 'warn' THEN 2 WHEN 'idle' THEN 1 ELSE 0 END)
                THEN EXCLUDED.tone ELSE system_check_day.tone END"""),
            {"k": key, "d": day, "t": tone})
        if changed:
            out.append({"key": key, "title": c.get("title"), "from": prev[0] if prev else None, "to": tone,
                        "down_since": prev[1] if prev else None, "check": c})
    db.commit()
    return out


def read(db: Session, keys: Iterable[str], now: Optional[datetime] = None) -> Dict[str, dict]:
    """{ключ: {tone, since, hist[14], last_failure, last_failure_at, last}} — история старшими днями вперёд."""
    keys = list(keys)
    now = now or datetime.utcnow()
    today = _msk(now).date()
    first = today - timedelta(days=DAYS - 1)
    out = {k: {"tone": None, "since": None, "last": None, "last_failure": None, "last_failure_at": None,
               "hist": [{"day": (first + timedelta(days=i)).isoformat(), "tone": None} for i in range(DAYS)]}
           for k in keys}
    for k, tone, since, last, lf, lfa in db.execute(text(
            "SELECT check_key, tone, since, last, last_failure, last_failure_at FROM system_check_state "
            "WHERE check_key = ANY(:k)"), {"k": keys}).all():
        out[k].update(tone=tone, since=since, last=last, last_failure=lf, last_failure_at=lfa)
    for k, d, tone in db.execute(text(
            "SELECT check_key, day, tone FROM system_check_day WHERE check_key = ANY(:k) AND day >= :d"),
            {"k": keys, "d": first}).all():
        out[k]["hist"][(d - first).days]["tone"] = tone
    return out


def _days(n: int) -> str:
    m, h = n % 10, n % 100
    word = "дней" if 11 <= h <= 14 else "день" if m == 1 else "дня" if 2 <= m <= 4 else "дней"
    return f"{n} {word}"


def since_label(tone: str, group: str, since: Optional[datetime], now: Optional[datetime] = None) -> Optional[str]:
    """Вторая строка под значением у warn/bad: «с 14.11 · 3 дня», «с 14:05» (сегодня), «жёлтый с 07.11» (ключи)."""
    if tone not in ("bad", "warn") or since is None:
        return None
    now = now or datetime.utcnow()
    s, n = _msk(since), _msk(now)
    if group == "keys" and tone == "warn":
        return f"жёлтый с {s.strftime('%d.%m')}"
    if s.date() == n.date():
        return f"с {s.strftime('%H:%M')}"
    return f"с {s.strftime('%d.%m')} · {_days((n.date() - s.date()).days + 1)}"
