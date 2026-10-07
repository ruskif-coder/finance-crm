# -*- coding: utf-8 -*-
"""Уборка проверок креатива по сроку (крон): `python -m app.creative_check.cleanup`.

Проверка живёт 48 часов (владелец 07.10.2026). Каждая просроченная — остановка нацеливания в DSP,
затем удаление файлов и строки. Не остановленная остаётся до следующего прохода; код выхода 1 —
хоть одна осталась (крон заметит).
"""
import sys

import app.model_registry  # noqa: F401 — крон идёт отдельным процессом, без роутеров
from app.creative_check.service import cleanup_expired
from app.database import SessionLocal


def run() -> dict:
    db = SessionLocal()
    try:
        return cleanup_expired(db)
    finally:
        db.close()


if __name__ == "__main__":
    out = run()
    print(f"Проверок креатива убрано: {out['removed']}"
          + (f"; осталось (DSP не ответил): {'; '.join(out['kept'])}" if out["kept"] else ""))
    sys.exit(1 if out["kept"] else 0)
