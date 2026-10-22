# -*- coding: utf-8 -*-
"""Код креатива (пары) — номер внутри размещения (аудит v2.6.0→v2.7.0, D4; 21.10.2026).

Номер = число уже названных пар + 1. Без блокировки два одновременных «ок» по разным парам одной площадки получали один код
`DEAL-PUB-0N`, а он уходит в DSP и ЕРИД; двойной ответ по одной паре перезаписывал вердикт и выдавал новый номер уже
после отправки в DSP. Теперь: строка ответа и строка размещения — под замком; уникальный индекс — последняя страховка."""
import inspect

from sqlalchemy import event, text

import app.model_registry  # noqa: F401


def test_numbering_locks_the_target_row():
    from app.database import SessionLocal
    from app.routers import launch_prep as R
    db = SessionLocal()
    seen = []
    try:
        tid = db.execute(text("SELECT id FROM launch_prep_target ORDER BY id LIMIT 1")).scalar() or 0
        event.listen(db.connection(), "before_cursor_execute", lambda c, cur, stmt, *a: seen.append(" ".join(stmt.split())))
        R._next_pair_no(db, tid)
    finally:
        db.rollback()
        db.close()
    assert any("FROM launch_prep_target" in q and "FOR UPDATE" in q for q in seen), seen


def test_publisher_verdict_reads_its_review_under_lock():
    from app.routers import launch_prep as R
    src = inspect.getsource(R.apply_platform_verdict)
    i = src.index('LaunchPrepReview.kind == "площадка").')
    assert "with_for_update()" in src[i:i + 120], "ответ площадки читает свою строку без блокировки"


def test_unique_index_migration_exists():
    import pathlib
    sql = (pathlib.Path(__file__).parent.parent / "migrations" / "2026-10-21_pair_code_unique.sql").read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in sql and "WHERE code IS NOT NULL" in sql
