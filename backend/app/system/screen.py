"""Сборка экрана «Статус системы» v2 (хендофф design_handoff_status, 16.11.2026) поверх проверок `status.collect`.

Проверки остаются там же и такими же; здесь к ним добавляется то, что появилось с хендоффом: группа по ключу,
«с какого момента» и история за 14 дней (`history`), идущий ручной запуск (`jobs`), прогноз диска (`disk`),
«Онлайн сейчас» (`presence`) и настройки оповещений (`alerts`). Тон секции и экрана считает фронт из строк.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import timez
from app.system import alerts, disk, history, jobs, presence
from app.system import status as st

# Группы экрана по порядку хендоффа: ключ, название. Группы проверок в `status.py` — русские слова; две старые
# («Конфигурация», «Бэкапы») сведены в одну, как в макете.
GROUPS = [("services", "Службы"), ("disk", "Диск и файлы"), ("db", "Базы"), ("external", "Внешние связи"),
          ("keys", "Ключи и сертификаты"), ("config", "Конфигурация и бэкапы"), ("jobs", "Фоновые задания")]
GROUP_OF = {"Службы": "services", "Диск": "disk", "Базы": "db", "Внешние связи": "external",
            "Ключи и сертификаты": "keys", "Конфигурация": "config", "Бэкапы": "config", "Фоновые задания": "jobs"}
# Кнопка «куда идти» у строки — только туда, где вопрос действительно решается.
ACTIONS = {"job_bidder": {"label": "Открыть Биддер", "href": "/traffic/bidder"}}


def _remembered(db: Session, have: set) -> list:
    """Живые проверки (наружу) и обход хранилища при открытии экрана не выполняются — их строки берутся из снимка
    фонового прогона."""
    snap = history.read(db, [k for k in st.LIVE_KEYS + st.WALK_KEYS if k not in have])
    return [h["last"] for h in snap.values() if h.get("last")]


def _where(c: dict) -> Optional[str]:
    if c["key"].startswith("ext_") and c["tone"] != "ok" and c.get("keys"):
        return "правится в .env"
    if c["key"] == "cfg_debug" and c["tone"] != "ok":
        return "DEBUG в .env"
    if c["key"].startswith("ssl_") and c["tone"] in ("warn", "bad"):
        return "лог Caddy"
    return None


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    m, h = n % 10, n % 100
    return f"{n} " + (many if 11 <= h <= 14 else one if m == 1 else few if 2 <= m <= 4 else many)


def build(db: Session, data: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    if data is None:
        # Снимка обхода ещё нет (свежая выкладка, фоновый прогон не ходил) — обходим сейчас, иначе строк просто не будет
        fresh = all((history.read(db, [k]).get(k) or {}).get("last") for k in st.WALK_KEYS)
        data = st.collect(db, live=False, walk=not fresh)
    checks = data["checks"]
    checks += _remembered(db, {c["key"] for c in checks})
    hist = history.read(db, [c["key"] for c in checks], now=now)
    run = st._safe_value(jobs.running, db, default={})
    for c in checks:
        c["gkey"] = GROUP_OF.get(c.get("group"), "services")
        h = hist.get(c["key"]) or {}
        same = h.get("tone") == c["tone"]
        c["since"] = (history.since_label(c["tone"], c["gkey"], h.get("since"), now) if same
                      else ("только что" if c["tone"] in ("bad", "warn") else None))
        c["hist"] = h.get("hist") or []
        c["last_failure"] = h.get("last_failure")
        c["runnable"] = c["key"] in jobs.JOBS
        r = run.get(c["key"])
        c["running"] = ({"at": timez.to_msk(r["started_at"]).strftime("%d.%m в %H:%M"), "by": r["by"]} if r else None)
        c["where"] = _where(c)
        c["action"] = c.get("action") or ACTIONS.get(c["key"]) if c["tone"] != "ok" else None

    samples = st._safe_value(disk.load, db, now.date(), default=[])
    fc = disk.forecast(samples, st.DISK_WARN_PCT)
    data["disk"] = {**data.get("disk", {}), "forecast": fc, "warn_pct": st.DISK_WARN_PCT,
                    "crit_pct": st.DISK_CRIT_PCT,
                    "dirs": next((c.get("dirs") for c in checks if c["key"] == "storage"), None) or []}
    online = st._safe_value(presence.online, db, now, default=[])
    data["online"] = online
    cfg = alerts.config(db)
    admins = st._safe_value(lambda: db.execute(text(
        "SELECT count(*) FROM users u JOIN roles r ON r.id = u.role_id WHERE r.key = 'admin' AND u.is_active = 1")).scalar(),
        default=None)
    data["notify"] = {**cfg, "on": alerts.is_on(cfg), "admins": admins}
    data["groups"] = [{"key": k, "label": label} for k, label in GROUPS]

    bad = sum(1 for c in checks if c["tone"] == "bad")
    warn = sum(1 for c in checks if c["tone"] == "warn")
    ok = sum(1 for c in checks if c["tone"] == "ok")
    for k in data.get("kpi", []):
        if k["key"] == "passed":
            k["value"] = f"{ok} / {len(checks)}"
            k["hint"] = " · ".join(x for x in (
                bad and _ru_plural(bad, "отказ", "отказа", "отказов"),
                warn and _ru_plural(warn, "предупреждение", "предупреждения", "предупреждений")) if x) or "замечаний нет"
        elif k["key"] == "disk":
            k["hint"] = (f"до жёлтого порога ≈ {fc['weeks_to_warn']:.0f} нед." if fc and fc.get("weeks_to_warn") is not None
                         else "рост не заметен" if fc else f"порог жёлтый {st.DISK_WARN_PCT}%")
        elif k["key"] == "actions":
            users = (data.get("activity") or {}).get("users_24h", 0)
            k["hint"] = _ru_plural(users, "пользователь", "пользователя", "пользователей") + f" · онлайн {len(online)}"
    data["overall"] = "bad" if bad else "warn" if warn else "ok"
    return data
