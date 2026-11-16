# -*- coding: utf-8 -*-
"""Выгрузка журнала в Excel (макет design_handoff_journal, 16.11.2026; право — только администратор, решение 16.11).

Выгружается ВСЁ найденное по текущим фильтрам, повторы не сворачиваются: одна запись — одна строка. Потолок — `CAP`
строк: журнал растёт (20 тыс. на 16.11), и файл без предела однажды съел бы память процесса (макет, допущение 6).
Сверх потолка — отказ словами «сузьте период», а не обрезанный молча файл.
"""
import io
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.journal import details as dt
from app.journal import feed
from app.journal import sections as sc
from app.timez import MSK_OFFSET

CAP = 50_000
CHUNK = 2_000
HEAD = ["Дата", "Время", "Кто", "Контур", "Раздел", "Действие", "Код сделки", "Объект", "Детали"]


class TooMany(ValueError):
    pass


def count(db: Session, f: feed.Query) -> int:
    known = {"staff": feed._known_actions(db, "staff"), "cabinet": feed._known_actions(db, "cabinet")}
    sql, p = feed._union(db, f, known)
    return (db.execute(text(f"SELECT count(*) FROM ({sql}) u"), p).scalar() or 0) if sql else 0


def _rows(db: Session, f: feed.Query):
    known = {"staff": feed._known_actions(db, "staff"), "cabinet": feed._known_actions(db, "cabinet")}
    sql, p = feed._union(db, f, known)
    if not sql:
        return
    off = 0
    while True:
        rows = db.execute(text(f"SELECT * FROM ({sql}) u ORDER BY at DESC, src, id DESC OFFSET :off LIMIT :lim"),
                          {**p, "off": off, "lim": CHUNK}).all()
        if not rows:
            return
        objs = feed._objects(db, rows)
        for r in rows:
            yield r, objs.get((r.src, r.id)) or {}
        off += CHUNK


def build(db: Session, f: feed.Query) -> tuple:
    """(байты xlsx, число строк). Сверх `CAP` — TooMany."""
    n = count(db, f)
    if n > CAP:
        raise TooMany(f"Найдено {n:,} записей — больше {CAP:,} в один файл. Сузьте период или фильтры.".replace(",", " "))
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Журнал"
    ws.append(HEAD)
    for c in ws[1]:
        c.font = Font(bold=True)
    written = 0
    for r, o in _rows(db, f):
        at = r.at + timedelta(hours=MSK_OFFSET)
        who = f"{r.site} · {r.actor_name}" if r.src == "cabinet" and r.site else r.actor_name
        det = "" if r.src == "cabinet" else dt.humanize(r.action, r.details)
        ws.append([at.strftime("%d.%m.%Y"), at.strftime("%H:%M"), who or "",
                   "Кабинет паблишера" if r.src == "cabinet" else "Сотрудник",
                   sc.BY_ID[sc.section_of(r.src, r.action)].title, sc.label_of(r.src, r.action),
                   o.get("code") or "", o.get("label") or "", det])
        written += 1
    for col, w in zip("ABCDEFGHI", (11, 7, 30, 18, 14, 40, 10, 50, 70)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    from app.xlsx_safe import save_workbook
    save_workbook(wb, buf)          # детали журнала — текст людей: «=…» не должен стать формулой
    return buf.getvalue(), written
