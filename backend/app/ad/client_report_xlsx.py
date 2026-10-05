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
from openpyxl.styles import Alignment, Font
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple

from app.ad.client_report import Report

_TPL = os.path.join(os.path.dirname(__file__), "..", "templates")
TEMPLATE = os.path.abspath(os.path.join(_TPL, "client_report_template.xlsx"))
CHART_XML = os.path.abspath(os.path.join(_TPL, "client_report_chart.xml"))
SHEET = "Отчёт"
# Привязка графика владельца (v5): от колонки D (+смещение) строки 11, размер в EMU.
CHART_ANCHOR = {"col": 3, "colOff": 947057, "row": 10, "rowOff": 54428,
                "cx": 22261286, "cy": 2220686}
SAMPLE_TITLE, SAMPLE_HEAD, SAMPLE_DATA, SAMPLE_TOTAL = 19, 20, 21, 22
FIRST_FREE = 18
# Раскладка образца v4 (владелец 05.10.2026): площадки B:F (площадка, показы, клики, уники,
# CTR), подписи дней — H, дни с I, «ИТОГО» дней — сразу за последней датой (в образце AN).
B, C, D, E, F, H, G = 2, 3, 4, 5, 6, 8, 9
TOTAL_COL_SAMPLE = 40
NO_DATA = "—"       # уники: формулу даст владелец вместе с охватом
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
            self.put(top, G + i, _ddmm(d, year=False), s.head_day)
        self.put(top, self.total_col, "ИТОГО", s.head_total)
        last = max(vals) if vals else None
        shows, clicks, uniq, ctr, acc, run = [], [], [], [], [], 0
        for d in self.days:
            v = vals.get(d)
            past = bool(last and d <= last and (self.d_from is None or d >= self.d_from))
            sh = v["shows"] if v else (0 if past else None)
            ck = v["clicks"] if v else (0 if past else None)
            shows.append(sh)
            clicks.append(ck)
            uniq.append((v.get("uniques") if v else 0) if (past and self.model) else
                        (NO_DATA if past else None))
            ctr.append(_ctr(sh, ck) if past else None)
            run += sh or 0
            acc.append(run if past else None)
        tot_sh, tot_ck = sum(x or 0 for x in shows), sum(x or 0 for x in clicks)
        lines = (("Показы", shows, tot_sh, NUM), ("Клики", clicks, tot_ck, NUM),
                 ("Уники", uniq, sum(x for x in uniq if isinstance(x, int)) if self.model
                  else NO_DATA, NUM),
                 ("CTR %", ctr, _ctr(tot_sh, tot_ck), CTR),
                 ("Накопительно", acc, run, NUM))
        for k, (lab, row_vals, total, fmt) in enumerate(lines, start=1):
            self.put(top + k, H, lab, s.day_label)
            for i, v in enumerate(row_vals):
                self.put(top + k, G + i, v, s.day_num, fmt)
            self.put(top + k, self.total_col, total, s.day_total, fmt)
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


def _chart(ws, top_row, n_days) -> dict | None:
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
        ext=XDRPositiveSize2D(cx=CHART_ANCHOR["cx"], cy=CHART_ANCHOR["cy"]))
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
        "mp_title": f"Отчёт о размещении · {adv}" + (f" | {brand}" if brand else ""),
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
    return [m1 + timedelta(days=i) for i in range((nxt - m1).days)]


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
    refs = _chart(ws, top_row, len(days)) if chart_at else None
    for cr in rep.creatives:
        r = p.block(r, cr["label"], cr["by_placement"], cr["by_day"])
    # Фон однородный — как пустая ячейка образца (белый −5 %); значения и итоги белые, шапки
    # синие — их стили из образца. Правый край — две колонки за «ИТОГО» дней (AP при 31 дне):
    # владелец 05.10.2026 убрал лишнюю заливку в крайней правой колонке.
    bg = copy(samples.background.fill)
    for row in ws.iter_rows(min_row=FIRST_FREE, max_row=max(ws.max_row, r) + 2,
                            max_col=p.total_col + 2):
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
    ws.title = SHEET
    samples = _Samples(ws)
    ws_model = None
    if rep_model is not None:
        ws_model = wb.copy_worksheet(ws)           # копия шаблона ДО заполнения
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
    wb._client_chart_refs = refs
    return wb


WEEKS_SHEET = WEEKS_SHEET_BASE = "По неделям"
WEEKS_MAX_FONT = 14
PCT_CTR = '0.00%'


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
    календарной недели и у «ИТОГО» по три колонки — показы, клики, CTR. Дельты нет. Сначала вся
    РК, ниже — то же по каждому креативу. В комплекте «модель» клики и CTR — модель SIMB ID."""
    ws = wb.create_sheet(title)
    ws.sheet_view.showGridLines = False
    h = rep.head
    model = bool(h.get("model"))
    d2 = h.get("days_to") or h["period_to"]
    weeks = weeks_of(h["period_from"], max(d2, h["period_from"]), h.get("last_data"))
    groups = len(weeks) + 1                         # недели + «ИТОГО»
    last_col = C + 3 * groups - 1
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

    def triple(rr, col, sh, ck, num, fmt_num=NUM):
        put(rr, col, sh, num, fmt_num)
        put(rr, col + 1, ck, num, fmt_num)
        put(rr, col + 2, (ck / sh) if sh else None, num, PCT_CTR)

    def row_of(rr, label, days, text, num, total_style):
        cell = put(rr, B, label, text)
        if text is s.text:                      # названия площадок — по центру, как в примере
            cell.alignment = center
        for i, w in enumerate(weeks):
            col = C + 3 * i
            if w["future"]:
                for k in range(3):
                    put(rr, col + k, None, num)
                continue
            triple(rr, col, *sums(days, w["from"], w["to"]), num)
        tc = C + 3 * len(weeks)
        triple(rr, tc, *sums(days), total_style)
        for k in range(3):
            c = ws.cell(rr, tc + k)
            if c.font.sz and c.font.sz > WEEKS_MAX_FONT:
                c.font = Font(**{**{a: getattr(c.font, a) for a in ("name", "b", "i", "color")},
                                 "sz": WEEKS_MAX_FONT})
        ws.row_dimensions[rr].height = s.h.get("data")

    def table(r, title_text, site_days) -> int:
        put(r, B, title_text, s.section)
        ws.merge_cells(start_row=r, end_row=r, start_column=B, end_column=last_col)
        ws.row_dimensions[r].height = s.h.get("title")
        r += 1
        # две строки шапки: группы недель (объединены на 3 колонки) и подписи метрик
        put(r, B, None, s.head)
        put(r + 1, B, "Площадка", s.head)
        ws.merge_cells(start_row=r, end_row=r + 1, start_column=B, end_column=B)
        ws.cell(r, B).value = "Площадка"
        for g in range(groups):
            col = C + 3 * g
            if g < len(weeks):
                w = weeks[g]
                label = f"Нед. {g + 1}\n{_ddmm(w['from'], False)}–{_ddmm(w['to'], False)}"
                label += "\n(неполная)" if w["partial"] else ""
                style = s.head_day
            else:
                label, style = "ИТОГО", s.head_total
            for k in range(3):
                put(r, col + k, None, style)
                put(r + 1, col + k, sub[k], style).alignment = center
            ws.cell(r, col).value = label
            ws.cell(r, col).alignment = center
            ws.merge_cells(start_row=r, end_row=r, start_column=col, end_column=col + 2)
        ws.row_dimensions[r].height = 48
        ws.row_dimensions[r + 1].height = s.h.get("head")
        r += 2
        all_days: dict = {}
        for site in sorted(site_days, key=lambda k: -sum(v[0] for v in site_days[k].values())):
            row_of(r, site, site_days[site], s.text, s.day_num, s.day_total)
            for d, v in site_days[site].items():
                acc = all_days.setdefault(d, [0, 0])
                acc[0] += v[0]
                acc[1] += v[1]
            r += 1
        row_of(r, "ИТОГО:", all_days, s.total_text, s.total_num, s.total_num)
        ws.row_dimensions[r].height = s.h.get("total")
        return r + 2

    r = table(2, f"Показы по неделям · РК {h.get('code') or ''}", rep.site_days)
    for cr in rep.creatives:
        r = table(r, cr["label"], cr.get("site_days") or {})

    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 26
    for g in range(groups):
        for k, wdt in enumerate((13, 11, 11)):
            ws.column_dimensions[get_column_letter(C + 3 * g + k)].width = wdt
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
