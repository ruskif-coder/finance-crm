"""Прогноз диска: «рост 1,8 ГБ в неделю — до жёлтого порога ≈ 10 недель» (хендофф «Статус системы», 16.11.2026).

Замер занятости — раз в день (`sample`, из фонового прогона), прогноз — линейный по последним 28 дням, а не вписан
руками: прямая наименьших квадратов через дневные замеры. Меньше недели замеров — прогноза нет: по трём точкам
наклон гуляет на порядок.
"""
import shutil
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

WINDOW_DAYS = 28
MIN_SPAN_DAYS = 7
FLAT_GB_WEEK = 0.05          # меньше — «рост не заметен»: шум замера, а не тенденция
GB = 2 ** 30


def sample(db: Session, day: date, root: str) -> None:
    """Замер дня. Повтор за тот же день переписывает его: последний замер дня точнее первого."""
    total, used, _free = shutil.disk_usage(root)
    db.execute(text("""INSERT INTO system_disk_sample (day, used_bytes, total_bytes) VALUES (:d, :u, :t)
                       ON CONFLICT (day) DO UPDATE SET used_bytes = EXCLUDED.used_bytes, total_bytes = EXCLUDED.total_bytes"""),
               {"d": day, "u": used, "t": total})
    db.commit()


def load(db: Session, today: date) -> List[Tuple[date, int, int]]:
    return [tuple(r) for r in db.execute(text(
        "SELECT day, used_bytes, total_bytes FROM system_disk_sample WHERE day > :d ORDER BY day"),
        {"d": today - timedelta(days=WINDOW_DAYS + 1)}).all()]


def forecast(samples: List[Tuple[date, int, int]], warn_free_pct: float = 20) -> Optional[dict]:
    """{growth_gb_week, weeks_to_warn, flat} или None, если замеров меньше недели."""
    samples = sorted(samples)[-(WINDOW_DAYS + 1):]
    if len(samples) < 2 or (samples[-1][0] - samples[0][0]).days < MIN_SPAN_DAYS:
        return None
    d0 = samples[0][0]
    xs = [(d - d0).days for d, _, _ in samples]
    ys = [u for _, u, _ in samples]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)   # байт в день
    growth = slope * 7 / GB
    if growth < FLAT_GB_WEEK:
        return {"growth_gb_week": round(growth, 2), "weeks_to_warn": None, "flat": True}
    _, used, total = samples[-1]
    left = total * (1 - warn_free_pct / 100) - used
    return {"growth_gb_week": growth, "weeks_to_warn": max(0.0, left / GB / growth), "flat": False}
