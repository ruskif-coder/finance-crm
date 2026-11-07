# -*- coding: utf-8 -*-
"""«С какого момента сайт в текущем статусе» (07.11.2026, замер скорости экранов): коррелированный подзапрос считал последнюю
смену статуса для КАЖДОЙ проверки — 22 тыс. строк × сотни проверок адреса, конвейер трафика ждал 3,4 с. Набором — то же самое.
Прибор: новый `latest` отдаёт ровно то, что давал прежний запрос (он здесь — как эталон), на данных стенда. Записей нет."""
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.traffic import site_monitor as SM

OLD_SINCE = """
    SELECT c.url, min(c.checked_at) AS since, count(*) AS streak
      FROM site_checks c
      JOIN (SELECT DISTINCT ON (url) url, status FROM site_checks
             ORDER BY url, checked_at DESC, id DESC) l ON l.url = c.url
     WHERE c.checked_at > coalesce((SELECT max(x.checked_at) FROM site_checks x
                                     WHERE x.url = c.url AND x.status <> l.status),
                                    'epoch'::timestamptz)
     GROUP BY c.url"""


def test_since_and_streak_match_the_old_query():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        old = {r["url"]: (r["since"], r["streak"]) for r in db.execute(text(OLD_SINCE)).mappings()}
        new = {u: (r.get("since"), r.get("streak")) for u, r in SM.latest(db).items()}
        assert new == old
    finally:
        db.rollback()
        db.close()


def test_since_query_is_not_correlated():
    import inspect
    assert "WHERE x.url = c.url" not in inspect.getsource(SM.latest), "подсчёт снова коррелированный — тормозит конвейер"
