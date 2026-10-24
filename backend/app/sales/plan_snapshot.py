# -*- coding: utf-8 -*-
"""Ночной снимок «Плана продаж» (владелец 24.10.2026): выполнение и прогноз каждой ячейки на сегодня — для «▲▼ за 7
дней». Истории светофора и стадий нет, поэтому прогноз недельной давности иначе не восстановить. Снимается текущий год
и, с декабря, следующий; хранится 90 дней (`plan.write_snapshot`).

Крон: `python -m app.sales.plan_snapshot` раз в сутки (docs/CRON_после_релиза.md). `--dry-run` — посчитать и не писать.
"""
import sys

import app.model_registry  # noqa: F401 — отдельный процесс: модели для внешних ключей
from app.database import SessionLocal
from app.sales import plan
from app.timez import msk_now


def run(dry: bool = False) -> dict:
    today = msk_now().date()
    years = [today.year] + ([today.year + 1] if today.month == 12 else [])
    db = SessionLocal()
    try:
        out = {}
        for y in years:
            cells = plan.aggregate(plan.deals_of(db, y))
            out[y] = len(cells) * 12 if dry else plan.write_snapshot(db, y, cells, today)
        return out
    finally:
        db.close()


if __name__ == "__main__":
    print(run(dry="--dry-run" in sys.argv))
