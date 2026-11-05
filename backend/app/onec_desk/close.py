# -*- coding: utf-8 -*-
"""Срок закрытия месяца и производственный календарь бухгалтерии (2026-11-05_onec_desk_v2.sql, владелец 05.11.2026).

Закрываемый месяц — прошлый: в ноябре закрывают октябрь. Строки в `accounting_close` нет — срок 10-е число следующего месяца,
18:00 МСК, месяц открыт. `closed_until` — последний день последнего закрытого месяца: дата документа в нём — предупреждение.
Календарь — только исключения: праздники в будни и рабочие выходные; ожидание считает `rules.work_hours` по нему."""
import calendar as _cal
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.onec_desk.rules import MSK
from app.periods import MONTHS_GEN, MONTHS_NOM as MONTHS

CLOSE_DAY, CLOSE_HOUR = 10, 18


def work_calendar(db: Session) -> dict:
    rows = db.execute(text("SELECT day, is_workday FROM work_calendar")).all()
    return {"holidays": sorted(r.day.isoformat() for r in rows if not r.is_workday),
            "workdays": sorted(r.day.isoformat() for r in rows if r.is_workday)}


def sets(cal: dict) -> tuple:
    return ({date.fromisoformat(d) for d in cal["holidays"]}, {date.fromisoformat(d) for d in cal["workdays"]})


def closing_month(now: datetime) -> str:
    n = now.astimezone(MSK)
    y, m = (n.year, n.month - 1) if n.month > 1 else (n.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def default_close_at(month: str) -> datetime:
    y, m = (int(x) for x in month.split("-"))
    y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return datetime(y, m, CLOSE_DAY, CLOSE_HOUR, tzinfo=MSK)


def closed_until(db: Session) -> Optional[date]:
    m = db.execute(text("SELECT max(month) FROM accounting_close WHERE closed")).scalar()
    if not m:
        return None
    y, mo = (int(x) for x in m.split("-"))
    return date(y, mo, _cal.monthrange(y, mo)[1])


def settings(db: Session, now: datetime) -> dict:
    month = closing_month(now)
    row = db.execute(text("SELECT close_at, closed FROM accounting_close WHERE month = :m"), {"m": month}).first()
    close_at = row.close_at if row is not None else default_close_at(month)
    cu = closed_until(db)
    mo = int(month[5:])
    return {"close_at": close_at.astimezone(MSK).isoformat(), "close_month": MONTHS[mo - 1], "close_month_gen": MONTHS_GEN[mo - 1],
            "month": month, "month_closed": bool(row.closed) if row is not None else False,
            "closed_until": cu.strftime("%d.%m.%Y") if cu else None, "calendar": work_calendar(db)}


def save_close(db: Session, month: str, close_at: datetime, closed: bool, user) -> None:
    db.execute(text("""INSERT INTO accounting_close (month, close_at, closed, updated_by, updated_at)
                       VALUES (:m, :c, :x, :u, now())
                       ON CONFLICT (month) DO UPDATE SET close_at = :c, closed = :x, updated_by = :u, updated_at = now()"""),
               {"m": month, "c": close_at, "x": closed, "u": getattr(user, "id", None)})
