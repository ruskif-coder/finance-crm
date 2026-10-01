# -*- coding: utf-8 -*-
"""Начало «Деталей» в журнале для решения площадки по креативу (владелец 01.10.2026):
сначала — чей это кабинет и какая площадка, потом — что решили. Раньше запись говорила
только «комплект №5: ок», и по журналу нельзя было понять, кто ответил."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def verdict_prefix(db: Session, publisher_id) -> str:
    """«Кабинет <имя> · <площадка>: » — или только площадка, если кабинета нет."""
    if not publisher_id:
        return ""
    row = db.execute(text("""
        SELECT p.name AS pub, (SELECT c.name FROM cabinet_publisher cp
                                 JOIN cabinet c ON c.id = cp.cabinet_id
                                WHERE cp.publisher_id = p.id ORDER BY cp.added_at LIMIT 1) AS cab
          FROM sales_publishers p WHERE p.id = :p
    """), {"p": publisher_id}).first()
    if not row:
        return ""
    return (f"Кабинет {row.cab} · {row.pub}: " if row.cab else f"{row.pub}: ")
