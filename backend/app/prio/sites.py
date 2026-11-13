# -*- coding: utf-8 -*-
"""Площадки в системе приоритезации — вкладка «Приоритезация» админ панели трафика (владелец 13.11.2026). Номер площадки в
сервисе (`sales_publishers.prio_site_id`) — то, без чего запрос не уходит площадке, а «Запустить» не заводит РК; до этого
экрана поле можно было поставить только в базе. Подключена = номер задан.

Один номер — одна площадка: статистика сервиса раскладывается по кампаниям, но заведение РК и сверка «что лежит в сервисе»
идут по `site_id`, и общий номер у двух аптек отправил бы РК не той."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.prio import models as M
from app.prio.service import PrioError

MAX_ID = 2_147_483_647                       # колонка INTEGER — больше вызовет ошибку базы, а не понятный отказ
ACTIVE = (M.DRAFT, M.AT_SITE, M.REWORK, M.APPROVED, M.LIVE, M.STOPPED)     # всё, кроме отказа


def list_sites(db: Session) -> list:
    """Активные площадки (как «+ площадка» в запросе): номер в сервисе и сколько пар запросов по ней сейчас в работе."""
    rows = db.execute(text("""
        SELECT p.id, p.name, p.prio_site_id,
               (SELECT count(*) FROM prio_placements pp WHERE pp.publisher_id = p.id AND pp.status = ANY(:act))
          FROM sales_publishers p
         WHERE p.is_active AND coalesce(p.status, '') <> 'АРХИВ'
         ORDER BY (p.prio_site_id IS NULL), lower(p.name)"""), {"act": list(ACTIVE)}).all()
    return [{"id": r[0], "name": r[1], "site_id": r[2], "connected": r[2] is not None, "requests": int(r[3] or 0)}
            for r in rows]


def set_site(db: Session, publisher_id: int, site_id: Optional[int]) -> dict:
    """Поставить или снять номер площадки. → {name, was, now}. Без commit — его делает ручка."""
    row = db.execute(text("""SELECT name, prio_site_id FROM sales_publishers
                              WHERE id = :i AND is_active AND coalesce(status, '') <> 'АРХИВ'"""), {"i": publisher_id}).first()
    if row is None:                          # архивная — как отсутствующая: на вкладке её нет (ревью 13.11.2026)
        raise PrioError(404, "Площадка не найдена среди активных")
    if site_id is not None:
        if isinstance(site_id, bool) or not isinstance(site_id, int) or not 0 < site_id <= MAX_ID:
            raise PrioError(400, "ID в системе приоритезации — целое число больше нуля")
        other = db.execute(text("SELECT name FROM sales_publishers WHERE prio_site_id = :s AND id <> :i"),
                           {"s": site_id, "i": publisher_id}).scalar()
        if other:
            raise PrioError(409, f"ID {site_id} уже у площадки «{other}» — один номер может быть только у одной площадки")
    db.execute(text("UPDATE sales_publishers SET prio_site_id = :s WHERE id = :i"), {"s": site_id, "i": publisher_id})
    db.flush()
    return {"name": row[0], "was": row[1], "now": site_id}
