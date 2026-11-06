# -*- coding: utf-8 -*-
"""Выгрузка сверок месяца в Excel (владелец 06.11.2026, «Паблишеры → Взаимодействия»): первая вкладка — сводная, как
таблица на экране; дальше каждая площадка на своей вкладке — кампании месяца с планом, фактом и суммой. Файл наш,
внутренний: суммы в нём есть (площадке он не уходит — её файл — разаллокация)."""
from __future__ import annotations

from io import BytesIO
from typing import List, Optional

from sqlalchemy.orm import Session

from app.publisher_recon import board as B
from app.publisher_recon.razaloc import _sheet_title
from app.xlsx_safe import save_workbook

SUMMARY = ("Площадка", "Кампаний", "Окончено", "Наши показы", "Показы площадки", "Расхождение", "Итог показов",
           "CPM", "Сумма", "Статус", "Ответить до", "Согласовал")
SITE = ("Бренд", "Услуга", "Поверхность", "ЕРИД", "Статус", "Начало", "Конец", "План", "Факт", "Сумма")
FORMATS = {"Наши показы": "# ##0", "Показы площадки": "# ##0", "Расхождение": "# ##0", "Итог показов": "# ##0",
           "План": "# ##0", "Факт": "# ##0", "CPM": "# ##0.00", "Сумма": "# ##0.00",
           "Ответить до": "DD.MM.YYYY", "Начало": "DD.MM.YYYY", "Конец": "DD.MM.YYYY"}


def _date(v: Optional[str]):
    from datetime import date
    return date.fromisoformat(v[:10]) if v else None


def _summary_row(r: dict) -> list:
    status = "просрочено" if r.get("late") else r["status"]
    return [r["site"], r["total"], r["done"], r["ours"], r["theirs"], r["delta"], r["agreed"], r["cpm"],
            r["amount"], status, _date(r.get("due_at")), r.get("decided_by")]


def _site_row(c: dict) -> list:
    return [c["brand"], c["service"], c["surface"], c["erid"], c["status"], _date(c.get("date_from")),
            _date(c.get("date_to")), c["plan"], c["fact"], c["amount"]]


def _fill(ws, head, rows: List[list]) -> None:
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    ws.append(list(head))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append(r)
        for i, c in enumerate(head, 1):
            if c in FORMATS:
                ws.cell(ws.max_row, i).number_format = FORMATS[c]
    for i, c in enumerate(head, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(36, len(c) + 4))
    ws.freeze_panes = "A2"


def export_xlsx(db: Session, period: str) -> bytes:
    import openpyxl
    rows = B.month_rows(db, period)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сводная"
    _fill(ws, SUMMARY, [_summary_row(r) for r in rows])
    used = {"сводная"}
    places = B._placements(db, period)          # месяц читается один раз, а не заново на каждую площадку
    for r in rows:
        mine = [p for p in places if p["publisher_id"] == r["publisher_id"]]
        _fill(wb.create_sheet(_sheet_title(r["site"] or str(r["publisher_id"]), used)), SITE,
              [_site_row(c) for c in B.campaigns(db, mine)])
    buf = BytesIO()
    save_workbook(wb, buf)
    return buf.getvalue()
