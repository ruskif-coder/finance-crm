# -*- coding: utf-8 -*-
"""Отчёт клиенту по РК — Excel (владелец 05.10.2026). Данные — `app/ad/client_report`.

Шаблон `templates/client_report_template.xlsx` собран из правки владельца (пример v3):
* шапка (строки 1–17): лого, заголовок, агентство/рекламодатель/бренд/даты слева, график
  `{{chart}}` в центре, «Результат за период» справа (`{{t.*}}`);
* строки 19–22 — ОБРАЗЦЫ первого блока (правка владельца v4): 19 — заголовки раздела (B:F) и
  дней (H…), 20 — шапка таблиц, 21 — строка данных (площадки B:F, подпись дня H, дни с I,
  «ИТОГО» дней — AN), 22 — «ИТОГО»; пустая ячейка образца — фон листа.
  Каждый раздел отчёта повторяет первый блок их стилями; образцы затем удаляются.

Суточные срезы — по горизонтали на ВЕСЬ флайт (владелец: иначе файл «улетит в длину»):
будущие дни пустые. Фон листа — белая заливка, как в шаблоне. График повторяет оформление,
которое владелец задал в Excel (openpyxl при чтении графики теряет, поэтому — кодом).
Денег нет.
"""
from __future__ import annotations

import os
from copy import copy
from datetime import date, timedelta
from typing import Optional

import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple

from app.ad.client_report import Report

_TPL = os.path.join(os.path.dirname(__file__), "..", "templates")
TEMPLATE = os.path.abspath(os.path.join(_TPL, "client_report_template.xlsx"))
CHART_XML = os.path.abspath(os.path.join(_TPL, "client_report_chart.xml"))
SHEET = "Отчёт"
# Привязка графика — ровно из правки владельца 17.11.2026 (файл QZ9VNS v6): от колонки D (+818 029 EMU) строки 11,
# ширина 19 061 205 EMU на стандартное поле 31 дня. Поле шире (РК на два месяца) — ширина растёт пропорционально
# ширине поля (`_fit_header`). Область построения внутри графика (x, w) — в `client_report_chart.xml`, из той же правки.
# Своя формула «пиксели колонки» не годится: Excel владельца рисует колонки иначе, чем считает формула.
CHART_ANCHOR = {"col": 3, "colOff": 818029, "row": 10, "rowOff": 54428, "cy": 2220686}
CHART_CX_31 = 19061205
# Колонок дней — всегда не меньше 31 (владелец 17.11.2026): у короткого месяца хвост пустой и заштрихован, шапка и
# «ИТОГО» стоят на одном месте у любого месяца. Числа — только за реальные дни.
MIN_DAY_COLS = 31
TOTAL_W, MARGIN_W = 17.44140625, 3.109375   # ширины «ИТОГО» / чисел результата и поля за ней (правка владельца v2)
ZOOM = 68                            # масштаб всех листов при открытии (владелец 17.11.2026: 70, затем 68)
DAY_W = 8.33203125                   # все колонки дней (правка владельца v2, 17.11.2026)
METRIC_W = {5: 13.0, 6: 13.0}        # «Уники» и «CTR» (E, F) — 13, шаблон давал им 14 вместе с D (правка владельца v2)
DEFAULT_W = 8.88671875               # ширина колонки без описания в шаблоне
SAMPLE_TITLE, SAMPLE_HEAD, SAMPLE_DATA, SAMPLE_TOTAL = 19, 20, 21, 22
FIRST_FREE = 18
# Раскладка образца v4 (владелец 05.10.2026): площадки B:F (площадка, показы, клики, уники,
# CTR), подписи дней — H, дни с I, «ИТОГО» дней — сразу за последней датой (в образце AN).
B, C, D, E, F, H, G = 2, 3, 4, 5, 6, 8, 9
TOTAL_COL_SAMPLE = 40
NO_DATA = "—"       # уники не посчитаны (с 24.10.2026 они моделью SIMB ID и на листах факта)
NUM = "#,##0"
CTR = "0.00"


def _ddmm(d, year=True) -> str:
    if not isinstance(d, date):
        return "—"
    return d.strftime("%d.%m.%Y" if year else "%d.%m")


def _style(dst, src, number_format=None):
    dst.font, dst.fill = copy(src.font), copy(src.fill)
    dst.border, dst.alignment = copy(src.border), copy(src.alignment)
    dst.number_format = number_format or src.number_format


class _Samples:
    """Стили первого блока из шаблона — снимаются до удаления образцов."""

    def __init__(self, ws):
        g = lambda r, c: copy(ws.cell(r, c))   # noqa: E731
        self.background = g(SAMPLE_DATA, 1)    # фон листа (белый −5 %) — пустая ячейка образца
        self.section, self.days_title = g(SAMPLE_TITLE, B), g(SAMPLE_TITLE, H)
        self.head, self.head_day, self.head_total = g(SAMPLE_HEAD, B), g(SAMPLE_HEAD, G), \
            g(SAMPLE_HEAD, TOTAL_COL_SAMPLE)
        self.text, self.num = g(SAMPLE_DATA, B), g(SAMPLE_DATA, C)
        self.day_label, self.day_num = g(SAMPLE_DATA, H), g(SAMPLE_DATA, G)
        self.day_total = g(SAMPLE_DATA, TOTAL_COL_SAMPLE)
        self.total_text, self.total_num = g(SAMPLE_TOTAL, B), g(SAMPLE_TOTAL, C)
        self.h = {k: ws.row_dimensions[r].height for k, r in
                  (("title", SAMPLE_TITLE), ("head", SAMPLE_HEAD), ("data", SAMPLE_DATA),
                   ("total", SAMPLE_TOTAL))}


class _Painter:
    def __init__(self, ws, s: _Samples, days: list, model: bool = False, d_from=None):
        self.ws, self.s, self.days, self.model = ws, s, days, model
        self.d_from = d_from   # дни до начала периода — пустые, а не нули
        # Комплект «с поправкой» подписан в шапках: клики, уники и CTR там — модель SIMB ID.
        self.m = " (модель)" if model else ""
        self.total_col = G + len(days)
        # Добивочная колонка (дня в месяце нет) — штриховка поверх фона листа, а не пустая клетка «как ноль»
        bg = copy(s.background.fill.fgColor) if s.background.fill.fill_type else "FFFFFFFF"
        self.hatch = PatternFill(fill_type="lightUp", fgColor="FFD3D8E3", bgColor=bg)

    def put(self, r, c, value, proto, fmt=None):
        cell = self.ws.cell(r, c)
        cell.value = value
        _style(cell, proto, fmt)
        return cell

    def height(self, r, kind):
        if self.s.h.get(kind):
            self.ws.row_dimensions[r].height = self.s.h[kind]

    def block(self, r, title, placements, by_day, days_title="НАКОПИТЕЛЬНЫЕ ДАННЫЕ") -> int:
        """Раздел как первый блок шаблона. → первая свободная строка под ним."""
        ws, s = self.ws, self.s
        self.put(r, B, title, s.section)
        ws.merge_cells(start_row=r, end_row=r, start_column=B, end_column=F)
        self.put(r, H, days_title, s.days_title)
        ws.merge_cells(start_row=r, end_row=r, start_column=H, end_column=self.total_col)
        self.height(r, "title")
        r += 1
        top = r
        # площадки: B:F
        for i, t in enumerate(("Площадка", "Показы", f"Клики{self.m}", f"Уники{self.m}",
                               f"CTR %{self.m}")):
            self.put(r, B + i, t, s.head)
        self.height(r, "head")
        rr = r + 1
        for row in placements:
            self._metrics(rr, row["label"], row["shows"], row["clicks"], row.get("uniques"),
                          s.text, s.num)
            self.height(rr, "data")
            rr += 1
        uq = [x.get("uniques") for x in placements]
        self._metrics(rr, "ИТОГО:", sum(x["shows"] for x in placements),
                      sum(x["clicks"] for x in placements),
                      None if any(u is None for u in uq) else sum(uq), s.total_text, s.total_num)
        self.height(rr, "total")
        end_left = rr + 1
        # дни по горизонтали — на весь флайт, будущие пустые
        vals = {x["label"]: x for x in by_day}
        self.put(top, H, "Дата", s.head)
        for i, d in enumerate(self.days):
            self.put(top, G + i, _ddmm(d, year=False) if d else None, s.head_day)
        self.put(top, self.total_col, "ИТОГО", s.head_total)
        last = max(vals) if vals else None
        shows, clicks, uniq, ctr, acc, run = [], [], [], [], [], 0
        for d in self.days:
            v = vals.get(d)
            past = bool(d and last and d <= last and (self.d_from is None or d >= self.d_from))
            sh = v["shows"] if v else (0 if past else None)
            ck = v["clicks"] if v else (0 if past else None)
            shows.append(sh)
            clicks.append(ck)
            uniq.append(round((v.get("uniques") or 0) if v else 0) if past else None)
            ctr.append(_ctr(sh, ck) if past else None)
            run += sh or 0
            acc.append(run if past else None)
        tot_sh, tot_ck = sum(x or 0 for x in shows), sum(x or 0 for x in clicks)
        lines = (("Показы", shows, tot_sh, NUM), ("Клики", clicks, tot_ck, NUM),
                 ("Уники", uniq, sum(x for x in uniq if isinstance(x, int)), NUM),
                 ("CTR %", ctr, _ctr(tot_sh, tot_ck), CTR),
                 ("Накопительно", acc, run, NUM))
        for k, (lab, row_vals, total, fmt) in enumerate(lines, start=1):
            self.put(top + k, H, lab, s.day_label)
            for i, v in enumerate(row_vals):
                self.put(top + k, G + i, v, s.day_num, fmt)
            self.put(top + k, self.total_col, total, s.day_total, fmt)
        for i, d in enumerate(self.days):
            if d is None:
                for rr in range(top, top + len(lines) + 1):
                    ws.cell(rr, G + i).fill = copy(self.hatch)
        end_right = top + len(lines) + 1
        for x in range(top + 1, max(end_left, end_right)):
            if not ws.row_dimensions[x].height:
                self.height(x, "data")
        return max(end_left, end_right) + 1

    def _metrics(self, r, label, shows, clicks, uniques, text, num):
        self.put(r, B, label, text)
        self.put(r, C, shows, num, NUM)
        self.put(r, D, clicks, num, NUM)
        self.put(r, E, NO_DATA if uniques is None else uniques, num, NUM)
        self.put(r, F, _ctr(shows, clicks), num, CTR)


def _ctr(shows, clicks):
    return round(clicks / shows * 100, 2) if shows else None


def _chart(ws, top_row, n_days, cx: int) -> dict | None:
    """Место под график владельца. Сам график — его XML (`client_report_chart.xml`, правка в
    Excel 05.10.2026) без изменений, кроме ссылок на диапазоны: openpyxl ставит заготовку с
    ТОЧНОЙ привязкой владельца, `to_xlsx` подменяет её содержимое. → ссылки для подмены."""
    if n_days == 0:
        return None
    last = get_column_letter(G + n_days - 1)
    first, lab = get_column_letter(G), get_column_letter(H)
    ch = BarChart()
    ch.add_data(Reference(ws, min_col=G, max_col=G + n_days - 1, min_row=top_row + 1),
                from_rows=True)
    ch.anchor = OneCellAnchor(
        _from=AnchorMarker(col=CHART_ANCHOR["col"], colOff=CHART_ANCHOR["colOff"],
                           row=CHART_ANCHOR["row"], rowOff=CHART_ANCHOR["rowOff"]),
        ext=XDRPositiveSize2D(cx=cx, cy=CHART_ANCHOR["cy"]))
    ws.add_chart(ch)
    sh = f"'{ws.title}'!"
    return {"SHOWS_T": f"{sh}${lab}${top_row + 1}", "CAT": f"{sh}${first}${top_row}:${last}${top_row}",
            "SHOWS": f"{sh}${first}${top_row + 1}:${last}${top_row + 1}",
            "CLICKS_T": f"{sh}${lab}${top_row + 2}",
            "CLICKS": f"{sh}${first}${top_row + 2}:${last}${top_row + 2}"}


def _fill_header(ws, rep: Report):
    from app.routers.media_plans import _find_token_cell, _insert_logo, _sub_cell
    h, t = rep.head, rep.totals
    adv, brand = h.get("advertiser") or "—", h.get("brand")
    mapping = {
        "mp_title": f"Отчёт о размещении · {adv}" + (f" | {brand}" if brand else "")
                    + (f" · группа «{h['group']}»" if h.get("group") else ""),
        "mp_subtitle": f"SIMB-AD · {h.get('agency') or adv} · данные по {_ddmm(h.get('last_data'))}",
        "title": f"РК {h.get('code') or ''}".strip(),
        "agency": h.get("agency") or "—", "advertiser": adv, "brand": brand or "—",
        "period": f"{_ddmm(h['period_from'])} — {_ddmm(h['period_to'])}",
        "date_from": _ddmm(h.get("date_start")), "date_to": _ddmm(h.get("date_end")),
        "t.shows": t["shows"], "t.clicks": t["clicks"],
        "t.ctr": "—" if t["ctr"] is None else t["ctr"],
        "t.plan": "—" if t["plan"] is None else t["plan"],
        "t.done_pct": "—" if t["done_pct"] is None else t["done_pct"],
        "t.last_data": _ddmm(h.get("last_data")),
    }
    logo = _find_token_cell(ws, "logo")
    chart_at = _find_token_cell(ws, "chart")
    for row in ws.iter_rows(min_row=1, max_row=FIRST_FREE - 1):
        for cell in row:
            if isinstance(cell.value, str) and "{{" in cell.value:
                _sub_cell(cell, mapping)
    _insert_logo(ws, logo)
    return coordinate_to_tuple(chart_at) if chart_at else None


CHART_MARK_COL = 7                   # метка графика в шаблоне — G11
RESULT_L, RESULT_V = 40, 41          # «Результат за период» в шаблоне: подписи AN, числа AO
HEAD_LAST = 45                       # правее этой колонки шаблон шапку не оформляет


def _fit_header(ws, tc: int, background) -> int:
    """Шапка первого листа — по колонке «ИТОГО» таблиц `tc` (правка владельца 17.11.2026, файл QZ9VNS): заголовок до `tc`,
    «Результат за период» — последние четыре колонки (подписи tc−3…tc−1, числа в tc), заголовок графика E…tc−6, место
    графика E…tc−5, зазор tc−4, поле справа tc+1. Шаблон рисует это на постоянном AO — шапка торчала правее таблиц.
    → ширина графика в EMU."""
    merged = {str(m) for m in ws.merged_cells.ranges}
    for rng in ("M3:AO4", "M5:AO5", "AN9:AO10", "E9:AL10", "G11:AM16"):
        if rng in merged:
            ws.unmerge_cells(rng)
    # снимок блока результата и места графика до перекладки
    label_style = {r: copy(ws.cell(r, RESULT_L)._style) for r in range(9, 17)}
    value_style = {r: copy(ws.cell(r, RESULT_V)._style) for r in range(9, 17)}
    texts = {r: (ws.cell(r, RESULT_L).value, ws.cell(r, RESULT_V).value) for r in range(9, 17)}
    chart_style = copy(ws.cell(11, CHART_MARK_COL)._style)
    # правее «ИТОГО» шапки нет: поле tc+1 — фон без рамок, дальше — чистый лист
    for r in range(1, FIRST_FREE):
        for c in range(tc + 1, HEAD_LAST + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell.border = Border()
            cell.fill = copy(background) if c == tc + 1 else PatternFill(fill_type=None)
    # «Результат за период»
    for r in range(9, 17):
        for c in range(tc - 3, tc + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell._style = copy(value_style[r] if (c == tc and r >= 11) else label_style[r])
        ws.cell(r, tc - 3).value = texts[r][0]
        if r >= 11:
            ws.cell(r, tc).value = texts[r][1]
    ws.merge_cells(start_row=9, end_row=10, start_column=tc - 3, end_column=tc)
    for r in range(11, 17):
        ws.merge_cells(start_row=r, end_row=r, start_column=tc - 3, end_column=tc - 1)
    # заголовок отчёта и подзаголовок — до «ИТОГО»
    ws.merge_cells(start_row=3, end_row=4, start_column=13, end_column=tc)
    ws.merge_cells(start_row=5, end_row=5, start_column=13, end_column=tc)
    # заголовок графика и его место (стиль места — бывшей метки графика G11), зазор перед результатом — фон
    ws.merge_cells(start_row=9, end_row=10, start_column=E, end_column=tc - 6)
    for r in range(11, 17):
        for c in range(E, tc - 4):
            ws.cell(r, c)._style = copy(chart_style)
            ws.cell(r, c).value = None
    ws.merge_cells(start_row=11, end_row=16, start_column=E, end_column=tc - 5)
    for r in range(1, FIRST_FREE):    # зазор перед результатом — фоном, и край заголовка графика над местом графика
        for c in ((tc - 5, tc - 4) if r in (9, 10) else (tc - 4,)):
            if ws.cell(r, c).fill.fill_type is None:
                ws.cell(r, c).fill = copy(background)
    # значения слева (агентство … окончание РК, C11:C16) — на чистом белом, а не «белый −5 %» шаблона (правка владельца v7)
    for r in range(11, 17):
        cell = ws.cell(r, C)
        if cell.fill.fill_type:
            cell.fill = PatternFill(fill_type="solid", fgColor=Color(theme=0, tint=0.0))
    widths = {**ws._tpl_cols, **METRIC_W, **{c: DAY_W for c in range(G, tc)}, tc: TOTAL_W, tc + 1: MARGIN_W}
    _write_cols(ws, widths, upto=max(tc + 2, max(ws._tpl_cols)))
    field = _field_width(widths, tc)
    return round(CHART_CX_31 * field / _field_width(widths, G + MIN_DAY_COLS)) if tc > G + MIN_DAY_COLS else CHART_CX_31


def _field_width(widths: dict, tc: int) -> float:
    """Ширина поля графика E…tc−5 в единицах ширины колонок."""
    return sum(widths.get(c, DEFAULT_W) for c in range(E, tc - 4))


def _tpl_cols(ws) -> dict:
    """Ширины колонок шаблона по номеру колонки. Шаблон описывает их ДИАПАЗОНАМИ (J…L, N…AL одной записью); обращение
    `column_dimensions["K"]` заводит поверх диапазона отдельную запись шириной 13, и Excel получал пересекающиеся
    описания — ширины «не прописывались» (владелец 17.11.2026). Поэтому снимок — один раз, сразу после загрузки."""
    out = {}
    for dim in list(ws.column_dimensions.values()):
        if dim.width and dim.min and (dim.max or dim.min) < 200:   # хвост «до конца листа» — не разворачиваем
            for c in range(dim.min, (dim.max or dim.min) + 1):
                out.setdefault(c, dim.width)
    return out


def _write_cols(ws, widths: dict, upto: int) -> None:
    """Описание колонок листа заново — по одной записи на колонку, без диапазонов и пересечений."""
    from openpyxl.worksheet.dimensions import ColumnDimension, DimensionHolder
    holder = DimensionHolder(worksheet=ws)
    for c in range(1, upto + 1):
        letter = get_column_letter(c)
        holder[letter] = ColumnDimension(ws, index=letter, width=widths.get(c, DEFAULT_W), customWidth=True)
    ws.column_dimensions = holder


def _days_of(rep: Report) -> list:
    """Колонки дней — ПОЛНЫЕ календарные месяцы, в которые попадает период отчёта (владелец
    05.10.2026: РК на 15 дней «поехала» — шаблон, график и ширины рассчитаны на месяц).
    Дни вне периода остаются пустыми (`_Painter.d_from` / будущие дни)."""
    h = rep.head
    d1, d2 = h["period_from"], h.get("days_to") or h["period_to"]
    if not d1 or not d2 or d2 < d1:
        return []
    m1 = d1.replace(day=1)
    nxt = (d2.replace(day=28) + timedelta(days=4)).replace(day=1)
    days = [m1 + timedelta(days=i) for i in range((nxt - m1).days)]
    return days + [None] * max(0, MIN_DAY_COLS - len(days))


def _fill_main(ws, rep: Report, samples: _Samples, model: bool):
    """Основной лист отчёта: шапка, график, разделы. → ссылки для графика (или None)."""
    ws._charts = []   # образец графика из шаблона — строим свой на весь флайт
    for mr in list(ws.merged_cells.ranges):
        if mr.max_row >= FIRST_FREE:
            ws.unmerge_cells(str(mr))
    ws.delete_rows(FIRST_FREE, ws.max_row - FIRST_FREE + 1)
    chart_at = _fill_header(ws, rep)
    if model:   # «Результат за период» модели: клики и CTR подписаны как модель
        for row in ws.iter_rows(min_row=9, max_row=FIRST_FREE - 1):
            for cell in row:
                if cell.value in ("Клики", "CTR, %"):
                    cell.value = f"{cell.value}{MODEL_SUFFIX}"
    days = _days_of(rep)
    p = _Painter(ws, samples, days, model, rep.head["period_from"])
    r = FIRST_FREE + 1
    top_row = r + 1
    r = p.block(r, "ПО ПЛОЩАДКАМ И ПО ДНЯМ", rep.by_placement, rep.by_day)
    cx = _fit_header(ws, p.total_col, samples.background.fill)
    refs = _chart(ws, top_row, len(days), cx) if chart_at else None
    # группы креативов (владелец 24.10.2026) — между общим блоком и креативами
    for cr in rep.groups + rep.creatives:
        r = p.block(r, cr["label"], cr["by_placement"], cr["by_day"])
    # Фон однородный — как пустая ячейка образца (белый −5 %); значения и итоги белые, шапки
    # синие — их стили из образца. Правый край — ОДНА колонка за «ИТОГО» дней (правка владельца 17.11.2026; до неё — две,
    # с 05.10.2026), то же поле, что у шапки.
    bg = copy(samples.background.fill)
    for row in ws.iter_rows(min_row=FIRST_FREE, max_row=max(ws.max_row, r) + 2,
                            max_col=p.total_col + 1):
        for cell in row:
            if type(cell).__name__ != "MergedCell" and cell.value is None \
                    and cell.fill.fill_type is None:
                cell.fill = bg
    ws.sheet_view.showGridLines = False
    return refs


MODEL_SUFFIX = " (модель)"


def render(rep: Report, rep_model: Optional[Report] = None, template_path: str = TEMPLATE):
    """Книга: «Отчёт» и «По неделям» — факт; при `rep_model` ещё комплект «с поправкой»
    («Отчёт (модель)», «По неделям (модель)») — владелец 05.10.2026: два комплекта вкладок."""
    wb = openpyxl.load_workbook(template_path)
    ws = wb.active
    ws._tpl_cols = _tpl_cols(ws)     # до любых обращений к колонкам по букве
    ws.title = SHEET
    samples = _Samples(ws)
    ws_model = None
    if rep_model is not None:
        ws_model = wb.copy_worksheet(ws)           # копия шаблона ДО заполнения
        ws_model._tpl_cols = ws._tpl_cols
        ws_model.title = SHEET + MODEL_SUFFIX
    refs = []
    r1 = _fill_main(ws, rep, samples, model=False)
    if r1:
        refs.append((SHEET, r1))
    _weeks_sheet(wb, rep, samples)
    if ws_model is not None:
        r2 = _fill_main(ws_model, rep_model, samples, model=True)
        if r2:
            refs.append((ws_model.title, r2))
        _weeks_sheet(wb, rep_model, samples, title=WEEKS_SHEET_BASE + MODEL_SUFFIX)
        # порядок листов: Отчёт, По неделям, Отчёт (модель), По неделям (модель)
        wb._sheets.sort(key=lambda x: [SHEET, WEEKS_SHEET_BASE, SHEET + MODEL_SUFFIX,
                                       WEEKS_SHEET_BASE + MODEL_SUFFIX].index(x.title))
    for sheet in wb.worksheets:
        sheet.sheet_view.zoomScale = sheet.sheet_view.zoomScaleNormal = ZOOM
    wb._client_chart_refs = refs
    return wb


WEEKS_SHEET = WEEKS_SHEET_BASE = "По неделям"
WEEKS_MAX_FONT = 14
PCT_CTR = '0.00%'
PER = 3             # колонок у недели и у «ИТОГО»: показы, клики, CTR (охват — строкой над неделями, 16.11.2026)


def weeks_of(d1: date, d2: date, last: date | None) -> list:
    """Календарные недели (пн–вс), обрезанные по периоду отчёта. «Неполная» — текущая: данные
    есть, но не до её последнего дня (владелец 05.10.2026); «будущая» — данных ещё нет, пусто."""
    out, d = [], d1
    while d <= d2:
        end = min(d + timedelta(days=6 - d.weekday()), d2)
        future = last is None or d > last
        out.append({"from": d, "to": end, "future": future,
                    "partial": (not future) and last < end})
        d = end + timedelta(days=1)
    return out


def _weeks_sheet(wb, rep: Report, s: _Samples, title: str = WEEKS_SHEET) -> None:
    """Лист «По неделям» (вид — по примеру аккаунтов 05.10.2026): площадки строками, у каждой
    календарной недели и у «ИТОГО» по три колонки — показы, клики, CTR. Над неделями всей РК — строка «Охват» (владелец
    16.11.2026): по дням недели сумма охватов пар «площадка × креатив» = уники модели × (1 − повторные заходы в неделе) ×
    (1 − пересечение аудитории площадок), оба числа — из диапазонов настроек SIMB ID, фиксируются на день (`report_coef`);
    в «ИТОГО» — сумма недель. По площадкам охвата нет. Дельты нет. Сначала вся
    РК, ниже — то же по каждому креативу. В комплекте «модель» клики и CTR — модель SIMB ID."""
    ws = wb.create_sheet(title)
    ws.sheet_view.showGridLines = False
    h = rep.head
    model = bool(h.get("model"))
    d2 = h.get("days_to") or h["period_to"]
    weeks = weeks_of(h["period_from"], max(d2, h["period_from"]), h.get("last_data"))
    groups = len(weeks) + 1                         # недели + «ИТОГО»
    last_col = C + PER * groups - 1
    put = _Painter(ws, s, []).put
    sub = ("показы", "клики (модель)" if model else "клики", "ctr (модель)" if model else "ctr")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def sums(days: dict, d_from=None, d_to=None):
        sh = ck = 0
        for d, v in days.items():
            if d_from is None or d_from <= d <= d_to:
                sh += v[0]
                ck += v[1]
        return sh, ck

    def reach(site_days: dict, d_from, d_to) -> float:
        """Охват таблицы за дни [d_from, d_to] — сумма охватов площадок-дней (4-е число `site_days`), не меньше
        «показы ÷ частота МП»: частота недели не выше заложенной в медиаплане (17.11.2026, `report_coef.week_reach`)."""
        from app.ad.report_coef import week_reach
        cells = [v for days in site_days.values() for d, v in days.items() if d_from <= d <= d_to]
        return week_reach(sum((v[3] if len(v) > 3 else 0) or 0 for v in cells), sum(v[0] or 0 for v in cells),
                          h.get("mp_freq"))

    def triple(rr, col, sh, ck, num, fmt_num=NUM):
        put(rr, col, sh, num, fmt_num)
        put(rr, col + 1, ck, num, fmt_num)
        put(rr, col + 2, (ck / sh) if sh else None, num, PCT_CTR)

    def row_of(rr, label, days, text, num, total_style):
        cell = put(rr, B, label, text)
        if text is s.text:                      # названия площадок — по центру, как в примере
            cell.alignment = center
        for i, w in enumerate(weeks):
            col = C + PER * i
            if w["future"]:
                for k in range(PER):
                    put(rr, col + k, None, num)
                continue
            triple(rr, col, *sums(days, w["from"], w["to"]), num)
        tc = C + PER * len(weeks)
        triple(rr, tc, *sums(days), total_style)
        for k in range(PER):
            c = ws.cell(rr, tc + k)
            if c.font.sz and c.font.sz > WEEKS_MAX_FONT:
                c.font = Font(**{**{a: getattr(c.font, a) for a in ("name", "b", "i", "color")},
                                 "sz": WEEKS_MAX_FONT})
        ws.row_dimensions[rr].height = s.h.get("data")

    def reach_row(r, site_days) -> int:
        # «Охват» — строкой над неделями (владелец 16.11.2026; подпись «Охват», а не «Расчётный охват» — 17.11.2026):
        # число на неделю, в «ИТОГО» — сумма недель
        put(r, B, "Охват", s.total_text)
        acc_reach = 0
        for g in range(groups):
            col = C + PER * g
            if g < len(weeks):
                w = weeks[g]
                val = None if w["future"] else round(reach(site_days, w["from"], w["to"]))
                acc_reach += val or 0
            else:
                val = acc_reach
            for k in range(PER):
                put(r, col + k, None, s.total_num)
            put(r, col, val, s.total_num, NUM).alignment = center
            ws.merge_cells(start_row=r, end_row=r, start_column=col, end_column=col + PER - 1)
        ws.row_dimensions[r].height = s.h.get("total")
        return r + 1

    def table(r, title_text, site_days, with_reach=False) -> int:
        put(r, B, title_text, s.section)
        ws.merge_cells(start_row=r, end_row=r, start_column=B, end_column=last_col)
        ws.row_dimensions[r].height = s.h.get("title")
        r += 1
        # Охват — только у таблицы всей РК и только в выгрузке всей РК (владелец 17.11.2026), не в разбивке по креативам
        # и группам: охват — про аудиторию кампании целиком, по частям он складывался бы в число, которого нет
        if with_reach:
            r = reach_row(r, site_days)
        # две строки шапки: группы недель (объединены на PER колонок) и подписи метрик
        put(r, B, None, s.head)
        put(r + 1, B, "Площадка", s.head)
        ws.merge_cells(start_row=r, end_row=r + 1, start_column=B, end_column=B)
        ws.cell(r, B).value = "Площадка"
        for g in range(groups):
            col = C + PER * g
            if g < len(weeks):
                w = weeks[g]
                label = f"Нед. {g + 1}\n{_ddmm(w['from'], False)}–{_ddmm(w['to'], False)}"
                label += "\n(неполная)" if w["partial"] else ""
                style = s.head_day
            else:
                label, style = "ИТОГО", s.head_total
            for k in range(PER):
                put(r, col + k, None, style)
                put(r + 1, col + k, sub[k], style).alignment = center
            ws.cell(r, col).value = label
            ws.cell(r, col).alignment = center
            ws.merge_cells(start_row=r, end_row=r, start_column=col, end_column=col + PER - 1)
        ws.row_dimensions[r].height = 48
        ws.row_dimensions[r + 1].height = s.h.get("head")
        r += 2
        all_days: dict = {}
        for site in sorted(site_days, key=lambda k: -sum(v[0] for v in site_days[k].values())):
            row_of(r, site, site_days[site], s.text, s.day_num, s.day_total)
            for d, v in site_days[site].items():
                acc = all_days.setdefault(d, [0, 0, 0])
                acc[0] += v[0]
                acc[1] += v[1]
                acc[2] += v[2] if len(v) > 2 else 0
            r += 1
        row_of(r, "ИТОГО:", all_days, s.total_text, s.total_num, s.total_num)
        ws.row_dimensions[r].height = s.h.get("total")
        return r + 2

    r = table(2, f"Показы по неделям · РК {h.get('code') or ''}", rep.site_days, with_reach=not h.get("group"))
    for cr in rep.groups + rep.creatives:
        r = table(r, cr["label"], cr.get("site_days") or {})

    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 26
    for g in range(groups):
        for k, wdt in enumerate((13, 11, 11)):
            ws.column_dimensions[get_column_letter(C + PER * g + k)].width = wdt
    bg = copy(s.background.fill)
    for row in ws.iter_rows(min_row=1, max_row=r, max_col=last_col + 1):
        for cell in row:
            if type(cell).__name__ != "MergedCell" and cell.fill.fill_type is None:
                cell.fill = bg


def to_xlsx(rep: Report, rep_model: Optional[Report] = None) -> bytes:
    """Готовый файл: листы из `render` + график владельца в каждом основном листе со своими
    ссылками (графики пронумерованы в порядке добавления: факт, потом модель)."""
    import io
    import re
    import zipfile

    from app.xlsx_safe import save_workbook
    wb = render(rep, rep_model)
    raw = io.BytesIO()
    save_workbook(wb, raw)
    refs = getattr(wb, "_client_chart_refs", None) or []
    if not refs:
        return raw.getvalue()
    with open(CHART_XML, encoding="utf-8", newline="") as fh:   # байт в байт, как у владельца
        tpl = fh.read()
    charts = {}
    for n, (_sheet, r) in enumerate(refs, start=1):
        chart = tpl
        for k, v in r.items():
            chart = chart.replace("{{%s}}" % k, v)
        if re.search(r"\{\{\w+\}\}", chart):
            raise RuntimeError("в графике отчёта остались неподставленные метки")
        charts[f"xl/charts/chart{n}.xml"] = chart.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as zin, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, charts.get(item.filename) or zin.read(item.filename))
    return out.getvalue()
