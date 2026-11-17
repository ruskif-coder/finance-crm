"""Фоновый прогон проверок — крон раз в 10 минут: `python -m app.system.watch` (хендофф «Статус системы», 16.11.2026).

Делает то, чего не делает открытие экрана: живые запросы наружу (связь с Телеграмом, SSL), запись состояния и истории
(`history.record`), оповещения при смене состояния (`alerts`), суточную сводку предупреждений в 09:00 МСК, дневной
замер диска для прогноза и чистку отметок «онлайн» старше суток.
"""
import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import timez
from app.system import alerts, disk, history, presence
from app.system import status as st

log = logging.getLogger("finance.status")


def run_once(db: Session, now: datetime = None) -> dict:
    now = now or datetime.utcnow()
    data = st.collect(db, live=True)
    # Самый первый прогон (таблица состояний пуста — свежая выкладка) только записывает состояние: иначе каждая уже
    # красная проверка «перешла в отказ» разом, и администраторы получили бы залп о давно известном.
    first = not db.execute(text("SELECT EXISTS (SELECT 1 FROM system_check_state)")).scalar()
    transitions = history.record(db, data["checks"], now=now)
    sent = 0 if first else alerts.send(db, transitions, now=now)
    alerts.daily_warn(db, data["checks"], now=now)
    st._safe_value(disk.sample, db, timez.to_msk(now).date(), st.UPLOADS_ROOT, default=None)
    st._safe_value(presence.prune, db, default=None)
    log.info("прогон статуса: проверок %s, переходов %s, оповещений %s", len(data["checks"]), len(transitions), sent)
    return data


def main() -> None:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        data = run_once(db)
        bad = [c["key"] for c in data["checks"] if c["tone"] == "bad"]
        print(f"{timez.msk_now():%Y-%m-%d %H:%M} проверок {len(data['checks'])}, отказов {len(bad)} {bad or ''}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
