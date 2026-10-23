# -*- coding: utf-8 -*-
"""Будильники «Статусов продаж» — то, что нужно и ручкам, и крону сканера (владелец 23.10.2026). Отдельно от роутера:
крон уведомлений роутеры не подтягивает (`tests/test_cron_runs_without_routers.py`)."""
from sqlalchemy import text

from app.sales.status_models import SalesStatusReminder


def row_label(db, adv_id, brand_id, client) -> str:
    """Как строка называется человеку: «Рекламодатель · Бренд», рекламодатель или клиент вне справочника."""
    if client:
        return client
    a = db.execute(text("SELECT coalesce(nullif(short_name, ''), name) FROM sales_advertisers WHERE id = :a"), {"a": adv_id}).scalar()
    b = db.execute(text("SELECT name FROM sales_brands WHERE id = :b"), {"b": brand_id}).scalar() if brand_id else None
    return f"{a} · {b}" if b else (a or "—")


def due(db, today) -> list:
    """Сработки сканера: срок настал, ещё не отправлено. Пропущенный прогон не теряет будильник — уйдёт со следующим."""
    rows = (db.query(SalesStatusReminder).filter(SalesStatusReminder.sent_at.is_(None),
                                                 SalesStatusReminder.remind_on <= today).all())
    return [(r, row_label(db, r.advertiser_id, r.brand_id, r.client_name)) for r in rows]
