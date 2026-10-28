# -*- coding: utf-8 -*-
"""«Агентские условия» в Excel (владелец 27.10.2026): расчёт СК за месяц или квартал тем же деревом, что экран —
агентство → юрлицо → договор → сделки, суммы на каждом уровне; итоги по способу; партнёрская по получателям; «не закрыта»
отдельным листом; партнёрская — во вкладке спец. условий, здесь её нет. Суммы — ₽ без НДС. Палитра — значения светлой темы (в Excel переменных нет)."""
import io

from app.agency_terms import calc as C

RUB = '#,##0.00'
INK, MUTED, BORDER = "1C2433", "79839A", "E3E7F1"
LEVEL_FILL = {0: "ECEFFD", 1: "F6F7FB", 2: None}
HEAD = ["Агентство / юрлицо / договор / сделка", "Мастер-сделка", "Бренд", "Услуга", "База ДС без НДС, ₽",
        "Способ", "СК, %", "СК, ₽"]


def _styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style="thin", color=BORDER)
    return {"b": Font(bold=True, color=INK), "n": Font(color=INK), "m": Font(color=MUTED, italic=True),
            "border": Border(bottom=thin), "wrap": Alignment(vertical="top", wrap_text=True), "fill": PatternFill}


def _fill(st, color):
    return st["fill"](start_color=color, end_color=color, fill_type="solid") if color else None


def _put(ws, row, values, st, bold=False, color=None, indent=0):
    from openpyxl.styles import Alignment
    for col, v in enumerate(values, 1):
        c = ws.cell(row=row, column=col, value=v)
        c.font = st["b"] if bold else st["n"]
        c.border = st["border"]
        if color:
            c.fill = _fill(st, color)
        if col >= 5 and col != 6:
            c.number_format = RUB if col != 7 else '0.00'
        if col == 1 and indent:
            c.alignment = Alignment(indent=indent)


def export(db, period: str, filters=None) -> bytes:
    from openpyxl import Workbook
    data = C.calc(db, period, filters)
    st = _styles()
    wb = Workbook()
    ws = wb.active
    ws.title = "Расчёт СК"
    closed = ", ".join(f"{m['period']} — {'закрыт' if m['closed'] else 'открыт'}" for m in data["months"])
    ws.append([f"Агентские условия · расчёт СК за {period}"])
    ws["A1"].font = st["b"]
    ws.append([f"Месяцы: {closed}. В расчёте — сделки, чья мастер-сделка прошла согласования в ДО."])
    ws["A2"].font = st["m"]
    ws.append([])
    _put(ws, 4, HEAD, st, bold=True, color=LEVEL_FILL[1])
    row = 5
    for s in data["tree"]:
        _put(ws, row, [s["name"], None, None, None, s["base_net"], None, None, s["main_amount"]], st, True, LEVEL_FILL[0])
        row += 1
        for e in s["entities"]:
            _put(ws, row, [e["name"], None, None, None, e["base_net"], None, None, e["main_amount"]], st, True,
                 LEVEL_FILL[1], indent=1)
            row += 1
            for c in e["contracts"]:
                _put(ws, row, [c["name"], None, None, None, c["base_net"], None, None, c["main_amount"]], st, True,
                     indent=2)
                row += 1
                for d in c["deals"]:
                    m = d["main"]
                    _put(ws, row, [f"{d['code']} — {d.get('title') or ''}", d.get("master_code"), d.get("brand"),
                                   d.get("service"), d["base_net"], m.get("mode") or "условие не задано", m.get("percent"),
                                   m.get("amount")], st, indent=3)
                    row += 1
    t = data["totals"]
    row += 1
    _put(ws, row, ["Итого база", None, None, None, t["base_net"], None, None, None], st, True, LEVEL_FILL[0])
    for mode, amount in sorted(t["by_mode"].items()):
        row += 1
        _put(ws, row, [f"СК · {mode}", None, None, None, None, mode, None, amount], st, True)
    if t["no_rule"]:
        row += 1
        _put(ws, row, [f"Без условия СК: сделок {t['no_rule']}", None, None, None, None, None, None, None], st)
    for col, w in zip("ABCDEFGH", (58, 14, 18, 16, 18, 15, 9, 15)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"

    ow = wb.create_sheet("Не закрыты")
    ow.append(["Сделка", "Агентство", "Юрлицо", "Договор", "Оценка по сделке, ₽ без НДС", "Способ", "СК, %", "Мастер-сделка"])
    for o in data["open"]:
        ow.append([f"{o['code']} — {o.get('title') or ''}", o["side"], o["entity"], o["contract"], o.get("estimate_net"),
                   o.get("mode") or "условие не задано", o.get("percent"), o.get("master_code") or "не в пакете"])
    for col, w in zip("ABCDEFGH", (50, 26, 30, 26, 22, 16, 9, 16)):
        ow.column_dimensions[col].width = w

    from app.xlsx_safe import save_workbook      # единственная точка сохранения: гасит формулы в ячейках из данных
    buf = io.BytesIO()
    save_workbook(wb, buf)
    return buf.getvalue()
