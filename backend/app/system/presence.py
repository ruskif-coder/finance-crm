"""«Онлайн сейчас» — сотрудники, открывшие страницу за последние 10 минут (хендофф «Статус системы», 16.11.2026).

Отметку ставит фронт при каждом открытии страницы (`POST /api/system/hit`). Пользователи кабинетов паблишеров сюда
не попадают по устройству: кабинет — отдельный сервис со своими учётками, в `users` их нет. Отметки хранятся сутки —
их чистит фоновый прогон (`prune`).
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

WINDOW_MIN = 10
LIVE_MIN = 2                 # зелёная метка присутствия — активность за последние 2 минуты
DEDUP_S = 15                 # повтор той же страницы тем же человеком чаще — одна отметка (перерисовки, двойной рендер)
KEEP_H = 24


def hit(db: Session, user_id: int, path: str) -> None:
    path = (path or "/")[:300]
    db.execute(text("""
        INSERT INTO user_page_hit (user_id, path)
        SELECT :u, :p WHERE NOT EXISTS (
            SELECT 1 FROM user_page_hit WHERE user_id = :u AND path = :p AND at > now() - make_interval(secs => :s))"""),
        {"u": user_id, "p": path, "s": DEDUP_S})
    db.commit()


def online(db: Session, now: Optional[datetime] = None) -> List[dict]:
    """[{user_id, name, path, ago: [минут назад, …], live}] — по последней активности, свежие сверху."""
    now = now or datetime.utcnow()
    rows = db.execute(text("""
        SELECT h.user_id, u.name, h.path, h.at FROM user_page_hit h JOIN users u ON u.id = h.user_id
         WHERE h.at > :since ORDER BY h.at"""), {"since": now - timedelta(minutes=WINDOW_MIN)}).all()
    by = {}
    for uid, name, path, at in rows:
        u = by.setdefault(uid, {"user_id": uid, "name": name, "path": path, "ago": []})
        u["path"] = path
        u["ago"].append(round(max(0.0, (now - at).total_seconds() / 60), 1))
    out = sorted(by.values(), key=lambda u: min(u["ago"]))
    for u in out:
        u["live"] = min(u["ago"]) <= LIVE_MIN
    return out


def prune(db: Session, now: Optional[datetime] = None) -> None:
    """Заходы старше суток не нужны «Онлайну» и «Активности» — журнал наблюдений, не учётные данные."""
    cut = (now or datetime.utcnow()) - timedelta(hours=KEEP_H)
    db.execute(text("DELETE FROM user_page_hit WHERE at < :t"), {"t": cut})
    db.commit()
