# -*- coding: utf-8 -*-
"""Отчёт ОРД за месяц в Excel и обратно (владелец 11.11.2026). Колонки — как в образце «пример по выгрузке.xlsx», плюс
«Мастер-сделка» и «Сумма сделки в УПД с НДС» (пожелание владельца: «к каждой сделке мастер сделку и номер упд с суммой»)
и «Пометка». Разбор читает колонки по заголовкам, порядок в файле может быть любым."""
import io
import math
from datetime import date, datetime
from typing import List

from app.ord.month_report import ReportError

COLS = (("deal_code", "ID РК", 10), ("deal_title", "Название РК", 44), ("master_code", "Мастер-сделка", 13),
        ("upd_no", "УПД", 8), ("upd_date", "Дата УПД", 11), ("upd_gross", "Бюджет УПД с НДС", 16),
        ("deal_gross", "Сумма сделки в УПД с НДС", 16), ("domain", "сайт (домен)", 26), ("shows", "Показы", 12),
        ("clicks", "Клики", 9), ("erid", "ЕРИД", 16), ("amount", "Сумма на площадку", 16), ("note", "Пометка", 36))
REQUIRED = ("deal_code", "domain", "shows", "erid", "amount")
MONEY = ("upd_gross", "deal_gross", "amount")


def to_xlsx(rows: List[dict], month: date) -> bytes:
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    from app.xlsx_safe import save_workbook, xlsx_safe
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"ОРД {month:%m.%Y}"
    ws.append([title for _k, title, _w in COLS])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([xlsx_safe(r.get(k)) for k, _t, _w in COLS])
    for i, (k, _t, w) in enumerate(COLS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
        fmt = "#,##0.00" if k in MONEY else ("DD.MM.YYYY" if k == "upd_date" else ("#,##0" if k in ("shows", "clicks") else None))
        if fmt:
            for cell in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                cell[0].number_format = fmt
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    save_workbook(wb, buf)
    return buf.getvalue()


def _num(v, cast):
    if v in (None, ""):
        return None
    if isinstance(v, str):
        v = v.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ReportError(f"Не число: «{v}»")
    # бесконечность и «не число» Excel отдаёт строкой; предел — то, что держат колонки (BIGINT показов, NUMERIC(14,2) сумм)
    if not math.isfinite(f) or abs(f) >= (1e15 if cast is int else 1e12):
        raise ReportError(f"Число вне разумных пределов: «{v}»")
    return int(f) if cast is int else round(f, 2)


COL_TITLE = {k: t for k, t, _w in COLS}
# Длины колонок `ord_report_overrides` — длиннее в базу не ляжет (ревью 11.11.2026: падало 500 на записи).
MAX_LEN = {"deal_code": 16, "upd_no": 40, "domain": 255, "erid": 255}


def _check_len(r: dict) -> dict:
    for f, n in MAX_LEN.items():
        if len(r.get(f) or "") > n:
            raise ReportError(f"«{COL_TITLE[f]}» длиннее {n} знаков")
    return r


def _date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ReportError(f"Не дата: «{v}»")


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def parse_xlsx(data: bytes) -> List[dict]:
    """Строки файла как словари полей отчёта. Нет обязательных колонок или не число в числовой — ReportError."""
    import openpyxl
    try:
        ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).worksheets[0]
    except Exception:
        raise ReportError("Файл не читается как Excel (.xlsx)")
    it = ws.iter_rows(values_only=True)
    head = [(_text(h)).lower() for h in next(it, ())]
    pos = {k: head.index(t.lower()) for k, t, _w in COLS if t.lower() in head}
    missing = [t for k, t, _w in COLS if k in REQUIRED and k not in pos]
    if missing:
        raise ReportError("В файле нет колонок: " + ", ".join(missing))
    out = []
    for n, row in enumerate(it, start=2):
        get = lambda k: row[pos[k]] if k in pos and pos[k] < len(row) else None   # noqa: E731
        if not _text(get("deal_code")):
            continue
        try:
            out.append(_check_len({"deal_code": _text(get("deal_code")).upper(), "deal_title": _text(get("deal_title")),
                        "master_code": _text(get("master_code")), "upd_no": _text(get("upd_no")) or None,
                        "upd_date": _date(get("upd_date")), "upd_gross": _num(get("upd_gross"), float),
                        "domain": _text(get("domain")).lower(), "shows": _num(get("shows"), int) or 0,
                        "clicks": _num(get("clicks"), int) or 0, "erid": _text(get("erid")),
                        "amount": _num(get("amount"), float)}))
        except ReportError as e:
            raise ReportError(f"Строка {n}: {e}")
    return out
