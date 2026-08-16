"""Годовая выгрузка медиаплана в Excel: сводная + бриф + лист на каждый месяц.

Постановка — docs/SPEC_годовой_МП_в_Excel.md. Книга собирается по ПЛАНУ целиком
(рекламодатель + N брендов):

  «Сводная»  — макет design_handoff_annual_media_plan: матрица 12 месяцев × бренды,
               подытоги по бренду, кварталы, сводка и доп. услуги;
  «Бриф»     — брифы по каждому бренду отдельно (у трёх брендов три брифа, общего
               только шапка, поэтому таргетинги живут здесь, а не в шапке листов);
  «2026-03»… — месячный МП в привычном виде конструктора: тот же шаблон, те же
               формулы, но строки собраны по всем брендам и отбиты полосами.

Месячные листы рендерятся ТЕМ ЖЕ кодом, что и выгрузка одиночного МП
(media_plans.render_mp_sheet), а строки берутся из общего сборщика
(year_plan.mp_parts) — того самого, которым конвейер создаёт сделки. Иначе выгрузка
и сделки разошлись бы в цифрах, а расхождение здесь заметят не сразу.

Листы делаются только на месяцы с закупкой: состав вкладок сам показывает флайт.
"""
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Палитра макета (см. README хендоффа, раздел Design Tokens).
NAVY_900, NAVY_800, NAVY_700 = "0A1433", "0F1C48", "14265E"
TINT_200, TINT_100, TINT_150 = "DFE4F0", "EEF1F8", "E3E8F4"
GREY_075, GREY_INACTIVE, BORDER = "F4F5F8", "F7F7F8", "C6C8CC"
TEXT_MUTED = "6F7480"

MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн",
                "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_HDR = [m.capitalize() for m in MONTHS_SHORT]
QUARTERS = ["I кв", "II кв", "III кв", "IV кв"]

MONEY = "# ##0"
INT = "# ##0"

_thin = Side(style="thin", color=BORDER)
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

# Матрица: A — «Бренд / услуга», B..M — месяцы, N — итог за год.
C_NAME, C_JAN, C_TOTAL = 1, 2, 14


def _f(size=11, bold=False, color="1A1A1A"):
    return Font(name="Arial", size=size, bold=bold, color=color)


def _put(ws, r, c, v=None, font=None, fill=None, align=None, fmt=None, border=BOX):
    cell = ws.cell(r, c)
    # Хвост объединённой области — MergedCell: значение read-only, но стиль ставится.
    # Заливку и рамку по всей ширине объединения приходится красить поячеечно, иначе
    # у полосы бренда закрашена только первая клетка.
    if type(cell).__name__ != "MergedCell":
        cell.value = v
    cell.font = font or _f()
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    if align:
        cell.alignment = align
    if fmt:
        cell.number_format = fmt
    if border:
        cell.border = border
    return cell


CTR = Alignment(horizontal="center", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def flight_label(months: list) -> str:
    """[2,3,4,8,9] → «мар–май, сен–окт». Схлопывание в диапазоны — как в макете."""
    if not months:
        return "—"
    groups, cur = [], [months[0], months[0]]
    for x in sorted(months)[1:]:
        if x == cur[1] + 1:
            cur[1] = x
        else:
            groups.append(cur)
            cur = [x, x]
    groups.append(cur)
    return ", ".join(MONTHS_SHORT[a] if a == b else f"{MONTHS_SHORT[a]}–{MONTHS_SHORT[b]}"
                     for a, b in groups)


def month_items(line, m: int) -> list:
    """Услуги месяца в нормализованном виде.

    Через _norm_products, а не через year_plan._month_items: часть строк заполнена
    ещё старым интерфейсом и хранит голые id услуг вместо объектов. Читать их
    сырыми — значит молча потерять месяц целиком.
    """
    from app.routers.year_plan import _norm_products
    items = _norm_products(line.products).get(str(m)) or []
    return [it for it in items if it.get("ref_id") is not None]


def _parts(line, m, svc, add, items):
    from app.routers.year_plan import mp_parts
    return mp_parts(line, m, svc, add, items)


# ── сбор данных плана ────────────────────────────────────────────────────
def collect(db, lines, svc, add, names) -> dict:
    """Разложить строки-бренды плана по месяцам через общий сборщик МП.

    Возвращает бренды со списком услуг (сумма/показы по 12 месяцам), разовые услуги
    и множество месяцев с закупкой. Показы = объём строки МП: для CPM это штуки
    показов, для прочих форм расчёта — единицы этой формы; в сводной колонка так и
    называется «объём», без домысливания.
    """
    brands, extras, months_on = [], [], set()
    for line in lines:
        name = names["brand"].get(line.brand_id) or "Без бренда"
        services: dict = {}          # позиция → {cost[12], vol[12]}
        for m in range(12):
            items = month_items(line, m)
            if not items:
                continue
            months_on.add(m)
            rows, exs = _parts(line, m, svc, add, items)
            for r in rows:
                pos = r.get("position") or "—"
                # У услуги с раздельным прайсом (web/app) это РАЗНЫЕ тарифы — сливать их
                # в одну строку нельзя: в мета-строке осталась бы одна цена, а месяцы
                # считались бы по двум. Инвентарь попадает в ключ строки и в название.
                inv = r.get("inventory")
                label = f"{pos} · {inv.upper()}" if inv in ("web", "app") else pos
                is_cpm = str(r.get("model") or "").upper() == "CPM"
                slot = services.setdefault(label, {
                    "name": label, "model": r.get("model"), "unit_price": r.get("unit_price"),
                    "is_cpm": is_cpm, "cost": [0.0] * 12, "vol": [0.0] * 12})
                vol, price = r.get("volume") or 0, r.get("unit_price") or 0
                div = 1000 if is_cpm else 1
                # Округляем: объём получен обратным счётом из суммы и тарифа, и без
                # округления в сводной вылезает 499 999,9999 вместо 500 000. Объём
                # CPM — до штуки показа, прочие формы (Фикс, пакеты) — до сотых:
                # там 2,5 единицы это реальные полторы недели, а не ошибка ввода.
                slot["cost"][m] += round(vol * price / div, 2)
                slot["vol"][m] += round(vol) if is_cpm else round(vol, 2)
            for e in exs:
                extras.append({"brand": name, "name": e.get("name") or "—",
                               "period": e.get("period"), "total": e.get("total") or 0})
        if services or any(e["brand"] == name for e in extras):
            brands.append({"name": name, "line": line, "services": list(services.values())})
    return {"brands": brands, "extras": extras, "months": sorted(months_on)}


# ── лист «Сводная» ───────────────────────────────────────────────────────
def sheet_summary(ws, plan, data, names, vat_rate):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 34
    for c in range(C_JAN, C_JAN + 12):
        ws.column_dimensions[get_column_letter(c)].width = 13
    ws.column_dimensions[get_column_letter(C_TOTAL)].width = 15

    adv = names["adv"].get(plan.advertiser_id) or "—"
    brands = data["brands"]
    agency = "—"
    for b in brands:
        a = names["agency"].get((b["line"].brief or {}).get("agency_id"))
        if a:
            agency = a
            break

    # ── шапка
    ws.merge_cells(start_row=1, end_row=1, start_column=1, end_column=C_TOTAL)
    _put(ws, 1, 1, f"Сводный медиаплан · {plan.year} · {adv}",
         font=_f(16, True, NAVY_700), align=LEFT, border=None)
    ws.merge_cells(start_row=2, end_row=2, start_column=1, end_column=C_TOTAL)
    _put(ws, 2, 1,
         f"SIMB-AD · {agency} · брендов: {len(brands)} · суммы в таблицах до НДС",
         font=_f(10, color="3D3D3D"), align=LEFT, border=None)

    r = 4
    # ── блок идентификации плана
    _put(ws, r, 1, "ПЛАН", font=_f(11, True, NAVY_700), align=LEFT)
    ident = [("Агентство", agency), ("Рекламодатель", adv), ("Брендов", len(brands)),
             ("Период размещения", f"{plan.year}-01 — {plan.year}-12"),
             ("Месяцев с закупкой", len(data["months"]))]
    for i, (k, v) in enumerate(ident):
        _put(ws, r + 1 + i, 1, k, font=_f(10, True), align=LEFT)
        _put(ws, r + 1 + i, 2, v, font=_f(10), align=LEFT)
    ws.column_dimensions["B"].width = 16

    matrix_top = r + len(ident) + 3
    total_row = _matrix(ws, matrix_top, brands, data["months"])

    # ── ИТОГО за год (ссылается на строку портфеля — пересчитается вместе с ней)
    tl = get_column_letter(C_TOTAL)
    r2 = total_row + 2
    _put(ws, r2, 1, "ИТОГО ЗА ГОД", font=_f(11, True, NAVY_700), align=LEFT)
    extras_sum = sum(e["total"] for e in data["extras"])
    net_ref = f"{tl}{total_row}" + (f"+{_num(extras_sum)}" if extras_sum else "")
    for i, (k, formula, fmt) in enumerate([
            ("Стоимость до НДС", f"={net_ref}", MONEY),
            (f"НДС {round(vat_rate * 100)}%", f"=({net_ref})*{vat_rate}", MONEY),
            ("Стоимость с НДС", f"=({net_ref})*{1 + vat_rate}", MONEY)]):
        _put(ws, r2 + 1 + i, 1, k, font=_f(10, True), align=LEFT)
        _put(ws, r2 + 1 + i, 2, formula, font=_f(10, True), align=RIGHT, fmt=fmt,
             fill=TINT_100 if i == 2 else None)

    r3 = r2 + 5
    if data["extras"]:
        r3 = _extras_table(ws, r3, data["extras"]) + 2
    _brand_summary(ws, r3, brands, data["months"])


def _num(x):
    return f"{round(x, 2)}"


def _matrix(ws, top, brands, months):
    """Матрица «бренд/услуга × 12 месяцев». Возвращает строку ИТОГО ПОРТФЕЛЬ."""
    _put(ws, top - 1, 1, "БАЗОВЫЕ УСЛУГИ ПО МЕСЯЦАМ (в строке услуги — стоимость до НДС, "
                         "ниже — объём; «—» месяц вне флайта)",
         font=_f(10, True, NAVY_700), align=LEFT, border=None)

    # шапка: кварталы + месяцы
    _put(ws, top, 1, "Квартал", font=_f(10, True, "FFFFFF"), fill=NAVY_800, align=CTR)
    for q in range(4):
        c1 = C_JAN + q * 3
        ws.merge_cells(start_row=top, end_row=top, start_column=c1, end_column=c1 + 2)
        for c in range(c1, c1 + 3):
            _put(ws, top, c, None, fill=NAVY_800)
        _put(ws, top, c1, QUARTERS[q], font=_f(10, True, "FFFFFF"), fill=NAVY_800, align=CTR)
    ws.merge_cells(start_row=top, end_row=top + 1, start_column=C_TOTAL, end_column=C_TOTAL)
    _put(ws, top, C_TOTAL, "Итого за год\nдо НДС", font=_f(10, True, "FFFFFF"),
         fill=NAVY_900, align=CTR)
    _put(ws, top + 1, 1, "Бренд / услуга", font=_f(10, True, "FFFFFF"), fill=NAVY_700, align=CTR)
    for i in range(12):
        _put(ws, top + 1, C_JAN + i, MONTHS_HDR[i], font=_f(10, True, "FFFFFF"),
             fill=NAVY_700, align=CTR)

    r = top + 2
    brand_cost_rows = []
    for b in brands:
        ws.merge_cells(start_row=r, end_row=r, start_column=1, end_column=C_TOTAL)
        for c in range(1, C_TOTAL + 1):
            _put(ws, r, c, None, fill=TINT_200)
        _put(ws, r, 1, b["name"].upper(), font=_f(10, True, NAVY_700), fill=TINT_200, align=LEFT)
        r += 1
        cost_rows = []
        for s in b["services"]:
            price = s["unit_price"] or 0
            meta = f"{s['model'] or ''} {price:,.0f} ₽".replace(",", " ").strip()
            flight = flight_label([m for m in range(12) if s["cost"][m]])
            _put(ws, r, 1, s["name"], font=_f(10, True), align=LEFT)
            _put(ws, r + 1, 1, f"{meta} · флайт: {flight}", font=_f(8, color=TEXT_MUTED), align=LEFT)
            for i in range(12):
                on = bool(s["cost"][i])
                _put(ws, r, C_JAN + i, s["cost"][i] if on else "—",
                     font=_f(10), align=RIGHT if on else CTR, fmt=MONEY if on else None,
                     fill=None if on else GREY_INACTIVE)
                _put(ws, r + 1, C_JAN + i, s["vol"][i] if on else None,
                     font=_f(8, color=TEXT_MUTED), align=RIGHT, fmt=INT,
                     fill=None if on else GREY_INACTIVE)
            _sum_row_cell(ws, r, fill=GREY_075, bold=True)
            _sum_row_cell(ws, r + 1, fill=GREY_075, font=_f(8, color=TEXT_MUTED), fmt=INT)
            cost_rows.append(r)
            r += 2
        # подытог бренда
        _put(ws, r, 1, f"Итого {b['name']}", font=_f(10, True, NAVY_700), fill=TINT_100, align=LEFT)
        for i in range(12):
            col = get_column_letter(C_JAN + i)
            # Через список аргументов, а не через «+»: в месяцах вне флайта стоит «—»,
            # и сложение текста даёт #ЗНАЧ!, тогда как СУММ такие ячейки пропускает.
            f = ",".join(f"{col}{x}" for x in cost_rows)
            _put(ws, r, C_JAN + i, f'=IF(SUM({f})=0,"—",SUM({f}))' if cost_rows else "—",
                 font=_f(10, True, NAVY_700), fill=TINT_100, align=RIGHT, fmt=MONEY)
        _sum_row_cell(ws, r, fill=TINT_150, bold=True, color=NAVY_700)
        brand_cost_rows.append(r)
        r += 1

    # ── ИТОГО ПОРТФЕЛЬ
    _put(ws, r, 1, "ИТОГО ПОРТФЕЛЬ", font=_f(10, True, "FFFFFF"), fill=NAVY_700, align=LEFT)
    for i in range(12):
        col = get_column_letter(C_JAN + i)
        f = ",".join(f"{col}{x}" for x in brand_cost_rows)
        _put(ws, r, C_JAN + i, f'=IF(SUM({f})=0,"—",SUM({f}))' if brand_cost_rows else "—",
             font=_f(10, True, "FFFFFF"), fill=NAVY_700, align=RIGHT, fmt=MONEY)
    _sum_row_cell(ws, r, fill=NAVY_900, bold=True, color="FFFFFF")

    # суммы кварталов в шапке — ссылками на строку портфеля
    for q in range(4):
        c1 = C_JAN + q * 3
        rng = f"{get_column_letter(c1)}{r}:{get_column_letter(c1 + 2)}{r}"
        ws.cell(top, c1).value = f'=CONCATENATE("{QUARTERS[q]} · ",TEXT(SUM({rng}),"# ##0")," ₽")'
    return r


def _sum_row_cell(ws, r, fill=None, bold=False, color="1A1A1A", font=None, fmt=MONEY):
    a, b = get_column_letter(C_JAN), get_column_letter(C_JAN + 11)
    _put(ws, r, C_TOTAL, f"=SUM({a}{r}:{b}{r})",
         font=font or _f(10, bold, color), fill=fill, align=RIGHT, fmt=fmt)


def _extras_table(ws, r, extras):
    _put(ws, r, 1, "ДОПОЛНИТЕЛЬНЫЕ УСЛУГИ (разово, без показов)",
         font=_f(10, True, NAVY_700), align=LEFT, border=None)
    r += 1
    for i, h in enumerate(["Источник", "Позиция", "Бренд", "Период", "Стоимость до НДС"]):
        _put(ws, r, 1 + i, h, font=_f(10, True, "FFFFFF"), fill=NAVY_700, align=CTR)
    for e in extras:
        r += 1
        _put(ws, r, 1, "SIMB-AD", font=_f(10), align=CTR)
        _put(ws, r, 2, e["name"], font=_f(10), align=LEFT)
        _put(ws, r, 3, e["brand"], font=_f(10), align=LEFT)
        _put(ws, r, 4, f"{e['period']} · разово", font=_f(10), align=CTR)
        _put(ws, r, 5, e["total"], font=_f(10), align=RIGHT, fmt=MONEY)
    r += 1
    _put(ws, r, 1, "ИТОГО", font=_f(10, True, NAVY_700), fill=TINT_100, align=LEFT)
    for c in (2, 3, 4):
        _put(ws, r, c, None, fill=TINT_100)
    _put(ws, r, 5, f"=SUM(E{r - len(extras)}:E{r - 1})" if extras else 0,
         font=_f(10, True, NAVY_700), fill=TINT_100, align=RIGHT, fmt=MONEY)
    return r


def _brand_summary(ws, r, brands, months):
    _put(ws, r, 1, "СВОДКА ПО БРЕНДАМ ЗА ГОД", font=_f(10, True, NAVY_700), align=LEFT, border=None)
    r += 1
    # «Объём показов» суммирует ТОЛЬКО услуги с моделью CPM: у фикса и пакетов в этой
    # же ячейке лежат штуки размещений, и сложение их с показами дало бы число, которое
    # ничего не значит.
    for i, h in enumerate(["Бренд", "Флайты", "Объём показов (CPM)", "Стоимость до НДС", "Доля"]):
        _put(ws, r, 1 + i, h, font=_f(10, True, "FFFFFF"), fill=NAVY_700, align=CTR)
    first = r + 1
    for b in brands:
        r += 1
        active = sorted({m for s in b["services"] for m in range(12) if s["cost"][m]})
        cost = sum(sum(s["cost"]) for s in b["services"])
        vol = sum(sum(s["vol"]) for s in b["services"] if s.get("is_cpm"))
        _put(ws, r, 1, b["name"], font=_f(10, True), align=LEFT)
        _put(ws, r, 2, flight_label(active), font=_f(10, color="4A4A4A"), align=LEFT)
        _put(ws, r, 3, vol, font=_f(10), align=RIGHT, fmt=INT)
        _put(ws, r, 4, cost, font=_f(10, True), align=RIGHT, fmt=MONEY)
        _put(ws, r, 5, None, font=_f(10), align=RIGHT, fmt="0,0%")
    last = r
    for x in range(first, last + 1):
        ws.cell(x, 5).value = f"=IF(SUM($D${first}:$D${last})=0,\"\",D{x}/SUM($D${first}:$D${last}))"
    r += 1
    _put(ws, r, 1, "ИТОГО", font=_f(10, True, NAVY_700), fill=TINT_100, align=LEFT)
    _put(ws, r, 2, f"{len(months)} мес.", font=_f(10, True, NAVY_700), fill=TINT_100, align=LEFT)
    _put(ws, r, 3, f"=SUM(C{first}:C{last})", font=_f(10, True, NAVY_700), fill=TINT_100,
         align=RIGHT, fmt=INT)
    _put(ws, r, 4, f"=SUM(D{first}:D{last})", font=_f(10, True, NAVY_700), fill=TINT_100,
         align=RIGHT, fmt=MONEY)
    _put(ws, r, 5, 1, font=_f(10, True, NAVY_700), fill=TINT_100, align=RIGHT, fmt="0,0%")
    return r


# ── лист «Бриф» ──────────────────────────────────────────────────────────
BRIEF_FIELDS = [("audience", "Аудитория"), ("buys", "Покупают"), ("interests", "Интересы"),
                ("behavior", "Поведение"), ("competitors", "Конкуренты")]


def sheet_brief(ws, plan, data, names):
    """Бриф отдельным листом: у каждого бренда он свой, в общую шапку не помещается."""
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 70
    _put(ws, 1, 1, f"Брифы по брендам · {plan.year}", font=_f(14, True, NAVY_700),
         align=LEFT, border=None)
    r = 3
    for b in data["brands"]:
        br = b["line"].brief or {}
        tg = br.get("targeting") or {}
        ws.merge_cells(start_row=r, end_row=r, start_column=1, end_column=2)
        for c in (1, 2):
            _put(ws, r, c, None, fill=TINT_200)
        _put(ws, r, 1, b["name"].upper(), font=_f(11, True, NAVY_700), fill=TINT_200, align=LEFT)
        r += 1
        pairs = [("Агентство", names["agency"].get(br.get("agency_id")) or "—"),
                 ("Плательщик", names["cp"].get(br.get("payer_counterparty_id")) or "—"),
                 ("ГЕО", names["geo"].get(br.get("geo_id")) or "—"),
                 ("Ответственный сейлз", names["user"].get(br.get("sales_rep_id")) or "—"),
                 ("Аккаунт-менеджер", names["user"].get(br.get("account_manager_id")) or "—")]
        pairs += [(label, _join(tg.get(key))) for key, label in BRIEF_FIELDS]
        seas = br.get("seasonality") or []
        if any(seas):
            pairs.append(("Сезонность", ", ".join(
                f"{MONTHS_SHORT[i]} {seas[i]}" for i in range(min(12, len(seas))) if seas[i])))
        if br.get("text"):
            pairs.append(("Комментарий", br["text"]))
        for k, v in pairs:
            _put(ws, r, 1, k, font=_f(10, True), align=LEFT)
            _put(ws, r, 2, v, font=_f(10), align=LEFT)
            r += 1
        r += 1


def _join(v):
    if not v:
        return "—"
    if isinstance(v, list):
        vals = [str(x) for x in v if x not in (None, "")]
        return ", ".join(vals) if vals else "—"
    return str(v)


# ── сборка книги ─────────────────────────────────────────────────────────
def build_workbook(db, plan, lines, svc, add, names, template_path, vat_rate):
    from openpyxl import load_workbook
    from app.routers.media_plans import render_mp_sheet

    data = collect(db, lines, svc, add, names)
    wb = load_workbook(template_path)
    tpl = wb["МП"] if "МП" in wb.sheetnames else wb.active

    adv = names["adv"].get(plan.advertiser_id) or "—"
    for m in data["months"]:
        period = f"{plan.year}-{m + 1:02d}"
        rows, extras = [], []
        for line in lines:
            items = month_items(line, m)
            if not items:
                continue
            r, e = _parts(line, m, svc, add, items)
            if not (r or e):
                continue
            name = names["brand"].get(line.brand_id) or "Без бренда"
            if r:
                rows.append({"_band": name})     # полоса-разделитель бренда
                rows.extend(r)
            if e:
                # Доп. услуги тоже отбиваем: у нескольких брендов позиции называются
                # одинаково («Sales-Lift» у каждого), и без полосы строки неразличимы.
                extras.append({"_band": name})
                extras.extend(e)
        b0 = (lines[0].brief or {}) if lines else {}
        full = {
            "period": period, "advertiser": adv,
            "brand": f"Брендов: {len(data['brands'])}",
            "agency": names["agency"].get(b0.get("agency_id")) or "—",
            "geo": names["geo"].get(b0.get("geo_id")) or "—",
            "title": plan.title or f"Годовой план {plan.year}",
            # Таргетинги в шапку месячного листа не идут: у каждого бренда свой бриф,
            # общей строки не существует. Они на листе «Бриф».
            "targeting": {}, "created_at": None,
            "date_from": None, "date_to": None,
            "head_override": {
                "mp_title": f"Медиаплан · {adv} · {period}",
                "mp_subtitle": f"SIMB-AD · {period} · брендов: {len(data['brands'])} · "
                               f"таргетинги — на листе «Бриф»",
                "tg_audience": "см. лист «Бриф»", "tg_buys": "см. лист «Бриф»",
                "tg_interests": "см. лист «Бриф»", "tg_behavior": "см. лист «Бриф»",
                "tg_competitors": "см. лист «Бриф»",
            },
        }
        ws = wb.copy_worksheet(tpl)
        ws.title = period
        render_mp_sheet(ws, full, rows, extras)

    wb.remove(tpl)
    summary = wb.create_sheet("Сводная")
    brief = wb.create_sheet("Бриф")
    sheet_summary(summary, plan, data, names, vat_rate)
    sheet_brief(brief, plan, data, names)
    # Порядок листов: Сводная → Бриф → месяцы (создавались последними, поэтому переставляем).
    wb._sheets = [summary, brief] + [s for s in wb._sheets if s not in (summary, brief)]
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:
        pass
    return wb, data
