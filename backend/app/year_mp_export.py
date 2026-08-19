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

# Палитра причёсанного макета (эталон — «Годовой_МП_2026_BINNO», сверен 2026-08-16).
# HEAD/GREY/WHITE в эталоне заданы тема-цветами книги (theme3 и theme0 с tint −0.05);
# здесь они разрешены в конкретный RGB, чтобы вид не зависел от темы шаблона.
HEAD = "1F497D"          # шапки таблиц и подытоги брендов
NAVY_700 = "14265E"      # заголовки разделов и полосы брендов
GREY_BG, WHITE = "F2F2F2", "FFFFFF"
TEXT, TEXT_MUTED, TEXT_SOFT = "1A1A1A", "6F7480", "4A4A4A"

MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн",
                "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_HDR = [m.capitalize() for m in MONTHS_SHORT]
QUARTERS = ["I кв", "II кв", "III кв", "IV кв"]

# Числовые форматы эталона. ACC — бухгалтерский (разряды выровнены по колонке,
# ноль показывается прочерком), MONEY — простой разрядный для клеток месяцев,
# RUB — крупные итоги с рублём, PCT — доля бренда.
MONEY = "#\\ ##0"
INT = "#\\ ##0"
ACC = '_-* #,##0_-;\\-* #,##0_-;_-* "-"??_-;_-@_-'
RUB = '_-* #,##0\\ "₽"_-;\\-* #,##0\\ "₽"_-;_-* "-"??\\ "₽"_-;_-@_-'
PCT = "#,#00%"

# Рамка — пунктир: в эталоне сетка нарочно приглушена, чтобы читались цифры,
# а не линовка. Толстая нижняя черта отбивает заголовок раздела от его таблицы.
_dash = Side(style="dashed")
BOX = Border(left=_dash, right=_dash, top=_dash, bottom=_dash)
UNDERLINE = Border(bottom=Side(style="medium"))

# Лист с полями: A и P — узкие пустые колонки. Матрица: B — «Бренд / услуга»,
# C..N — месяцы, O — итог за год.
C_NAME, C_JAN, C_TOTAL = 2, 3, 15
C_PAD_L, C_PAD_R = 1, 16


def _f(size=11, bold=False, color=TEXT):
    return Font(name="Calibri Light", size=size, bold=bold, color=color)


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
def _span(ws, r, c1, c2, v=None, font=None, fill=None, align=None, fmt=None, border=BOX):
    """Объединение с прокраской всей ширины: у MergedCell стиль ставится поячеечно,
    иначе заливка и рамка остаются только на первой клетке."""
    if c2 > c1:
        ws.merge_cells(start_row=r, end_row=r, start_column=c1, end_column=c2)
    for c in range(c1, c2 + 1):
        _put(ws, r, c, None, font=font, fill=fill, align=align, border=border)
    return _put(ws, r, c1, v, font=font, fill=fill, align=align, fmt=fmt, border=border)


def _wash(ws, last_col, pad=2):
    """Залить лист серым до последней заполненной строки.

    Подложка — общий фон обеих вкладок: белым остаются только клетки с данными и
    итоговые строки, за счёт чего таблицы читаются как карточки на сером поле, а
    не как сетка. Красим последним шагом и только там, где заливки ещё нет, —
    иначе затрёт белые ячейки и акцентные шапки.
    """
    for r in range(1, ws.max_row + pad + 1):
        for c in range(1, last_col + 1):
            cell = ws.cell(r, c)
            if not cell.fill.patternType:
                cell.fill = PatternFill("solid", fgColor=GREY_BG)


def _caption(ws, r, c1, c2, text, rule_to=None):
    """Заголовок раздела: капс, толстая нижняя черта, светлая подложка.

    rule_to — докуда тянуть черту, если она шире объединения заголовка: у сводки
    по брендам подпись занимает не всю таблицу, а черта обязана дойти до её края,
    иначе обрывается на середине.
    """
    cap = _span(ws, r, c1, c2, text, font=_f(12, True, NAVY_700), fill=GREY_BG,
                align=LEFT, border=UNDERLINE)
    for c in range(c2 + 1, (rule_to or c2) + 1):
        _put(ws, r, c, None, fill=GREY_BG, border=UNDERLINE)
    return cap


def sheet_summary(ws, plan, data, names, vat_rate):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions[get_column_letter(C_PAD_L)].width = 2.9
    ws.column_dimensions[get_column_letter(C_NAME)].width = 35.6
    for c in range(C_JAN, C_JAN + 12):
        ws.column_dimensions[get_column_letter(c)].width = 13
    ws.column_dimensions[get_column_letter(C_TOTAL)].width = 15
    ws.column_dimensions[get_column_letter(C_PAD_R)].width = 2.8

    adv = names["adv"].get(plan.advertiser_id) or "—"
    brands = data["brands"]
    agency = "—"
    for b in brands:
        a = names["agency"].get((b["line"].brief or {}).get("agency_id"))
        if a:
            agency = a
            break

    _header_band(ws, plan, adv, agency, len(brands))

    # ── три блока в один ряд: ПЛАН · СВОДКА ПО БРЕНДАМ · ИТОГО ЗА ГОД.
    # Раскладка эталона: справочные данные читаются одним взглядом, а матрица
    # ниже начинается сразу под самым высоким из блоков.
    _caption(ws, 9, C_NAME, C_NAME + 1, "ПЛАН")
    _caption(ws, 9, 5, 9, "СВОДКА ПО БРЕНДАМ ЗА ГОД", rule_to=10)
    _caption(ws, 9, 12, C_TOTAL, "ИТОГО ЗА ГОД")
    ws.row_dimensions[9].height = 15

    ident = [("Агентство", agency), ("Рекламодатель", adv), ("Брендов", len(brands)),
             ("Период размещения", f"{plan.year}-01 — {plan.year}-12")]
    for i, (k, v) in enumerate(ident):
        _put(ws, 10 + i, C_NAME, k, font=_f(10, True), fill=GREY_BG, align=LEFT)
        _put(ws, 10 + i, C_NAME + 1, v, font=_f(10), fill=GREY_BG, align=LEFT)

    summary_bottom = _brand_summary(ws, 10, brands, data["months"])

    matrix_top = max(13, summary_bottom) + 2
    total_row = _matrix(ws, matrix_top, brands)

    # ── ИТОГО ЗА ГОД: ссылки на строку портфеля, поэтому блок пишется после
    # матрицы, хотя стоит выше неё.
    tl = get_column_letter(C_TOTAL)
    extras_sum = sum(e["total"] for e in data["extras"])
    net_ref = f"{tl}{total_row}" + (f"+{_num(extras_sum)}" if extras_sum else "")
    for i, (k, formula) in enumerate([
            ("Стоимость до НДС", f"={net_ref}"),
            (f"НДС {round(vat_rate * 100)}%", f"=({net_ref})*{vat_rate}"),
            ("Стоимость с НДС", f"=({net_ref})*{1 + vat_rate}")]):
        r = 11 + i
        _span(ws, r, 12, 13, k, font=_f(12, True), fill=GREY_BG, align=RIGHT)
        # Белая плашка под крупной суммой: подложка листа серая, и цифра, ради
        # которой открывают лист, должна с неё выступать.
        _span(ws, r, 14, C_TOTAL, formula, font=_f(14, color="000000"), fill=WHITE,
              align=CTR, fmt=RUB)

    if data["extras"]:
        _extras_table(ws, total_row + 3, data["extras"])
    _wash(ws, C_PAD_R)


def _num(x):
    """Число в текст формулы. Целое — без «.0»: сумма доп. услуг попадает прямо в
    формулу ИТОГО, и хвост дробной части там просто мусор перед глазами."""
    v = round(x, 2)
    return str(int(v)) if v == int(v) else str(v)


def _header_band(ws, plan, adv, agency, n_brands):
    """Шапка листа: полоса на всю ширину, слева место под логотип, справа —
    название и подпись. Отбита сверху тонкой, снизу толстой линией."""
    for r in range(1, 7):
        for c in range(C_PAD_L, C_PAD_R + 1):
            _put(ws, r, c, None, fill=GREY_BG, border=None)
        ws.row_dimensions[r].height = 14.4
    for c in range(C_NAME, C_TOTAL + 1):
        _put(ws, 1, c, None, fill=GREY_BG,
             border=Border(top=Side(style="thin"), bottom=Side(style="medium")))
        _put(ws, 6, c, None, fill=GREY_BG, border=UNDERLINE)
    ws.row_dimensions[6].height = 15

    # Логотип — та же картинка и тот же якорь, что на месячных листах (B3):
    # openpyxl теряет встроенные изображения при round-trip, поэтому лого не живёт
    # в шаблоне, а вставляется на каждый рендер.
    from app.routers.media_plans import _insert_logo
    ws.merge_cells(start_row=3, end_row=5, start_column=C_NAME, end_column=C_NAME + 2)
    _insert_logo(ws, f"{get_column_letter(C_NAME)}3")
    ws.merge_cells(start_row=3, end_row=4, start_column=9, end_column=C_TOTAL)
    _put(ws, 3, 9, f"Сводный медиаплан · {plan.year} · {adv}",
         font=_f(28, True, NAVY_700), fill=GREY_BG, align=RIGHT, border=None)
    _span(ws, 5, 9, C_TOTAL,
          f"SIMB-AD · {agency} · брендов: {n_brands} · суммы в таблицах до НДС",
          font=_f(10, color="3D3D3D"), fill=GREY_BG, align=RIGHT, border=None)


def _matrix(ws, top, brands):
    """Матрица «бренд/услуга × 12 месяцев». Возвращает строку ИТОГО ПОРТФЕЛЬ."""
    _span(ws, top, C_NAME, C_TOTAL,
          "БАЗОВЫЕ УСЛУГИ ПО МЕСЯЦАМ (в строке услуги — стоимость до НДС, "
          "ниже — объём; «—» месяц вне флайта)",
          font=_f(10, True, NAVY_700), fill=GREY_BG, align=LEFT, border=UNDERLINE)
    ws.row_dimensions[top].height = 15

    # шапка: кварталы + месяцы
    hdr = top + 1
    _put(ws, hdr, C_NAME, "Квартал", font=_f(10, True, WHITE), fill=HEAD, align=CTR)
    for q in range(4):
        c1 = C_JAN + q * 3
        _span(ws, hdr, c1, c1 + 2, QUARTERS[q], font=_f(10, True, WHITE), fill=HEAD, align=CTR)
    ws.merge_cells(start_row=hdr, end_row=hdr + 1, start_column=C_TOTAL, end_column=C_TOTAL)
    _put(ws, hdr + 1, C_TOTAL, None, fill=HEAD)
    _put(ws, hdr, C_TOTAL, "Итого за год\nдо НДС", font=_f(10, True, WHITE),
         fill=HEAD, align=CTR)
    _put(ws, hdr + 1, C_NAME, "Бренд / услуга", font=_f(10, True, WHITE), fill=HEAD, align=CTR)
    for i in range(12):
        _put(ws, hdr + 1, C_JAN + i, MONTHS_HDR[i], font=_f(10, True, WHITE),
             fill=HEAD, align=CTR)

    r = hdr + 2
    brand_cost_rows = []
    for b in brands:
        # Полоса бренда: белая с тёмно-синим капсом. Акцент здесь минимальный —
        # выделены подытоги, а не заголовки, иначе рябит.
        _span(ws, r, C_NAME, C_TOTAL, b["name"].upper(),
              font=_f(10, True, NAVY_700), fill=WHITE, align=LEFT)
        r += 1
        cost_rows = []
        for s in b["services"]:
            price = s["unit_price"] or 0
            meta = f"{s['model'] or ''} {price:,.0f} ₽".replace(",", " ").strip()
            flight = flight_label([m for m in range(12) if s["cost"][m]])
            _put(ws, r, C_NAME, s["name"], font=_f(10, True), fill=GREY_BG, align=LEFT)
            _put(ws, r + 1, C_NAME, f"{meta} · флайт: {flight}",
                 font=_f(8, color=TEXT_MUTED), fill=GREY_BG, align=LEFT)
            for i in range(12):
                on = bool(s["cost"][i])
                # Месяц вне флайта — прочерк по центру на подложке; месяц с закупкой —
                # число на белом, чтобы флайт читался пятнами белого в сером поле.
                _put(ws, r, C_JAN + i, s["cost"][i] if on else "—",
                     font=_f(10), align=RIGHT if on else CTR, fmt=MONEY if on else None,
                     fill=WHITE if on else GREY_BG)
                _put(ws, r + 1, C_JAN + i, s["vol"][i] if on else None,
                     font=_f(8, color=TEXT_MUTED), align=RIGHT, fmt=INT,
                     fill=WHITE if on else GREY_BG)
            _sum_row_cell(ws, r, fill=WHITE, bold=True, fmt=ACC)
            _sum_row_cell(ws, r + 1, fill=WHITE, font=_f(8, color=TEXT_MUTED), fmt=ACC)
            cost_rows.append(r)
            r += 2
        # подытог бренда — самая тёмная строка блока
        _put(ws, r, C_NAME, f"Итого {b['name']}", font=_f(10, True, WHITE), fill=HEAD, align=LEFT)
        for i in range(12):
            col = get_column_letter(C_JAN + i)
            # Через список аргументов, а не через «+»: в месяцах вне флайта стоит «—»,
            # и сложение текста даёт #ЗНАЧ!, тогда как СУММ такие ячейки пропускает.
            f = ",".join(f"{col}{x}" for x in cost_rows)
            _put(ws, r, C_JAN + i, f'=IF(SUM({f})=0,"—",SUM({f}))' if cost_rows else "—",
                 font=_f(10, True, WHITE), fill=HEAD, align=RIGHT, fmt=MONEY)
        _sum_row_cell(ws, r, fill=HEAD, bold=True, color=WHITE, fmt=ACC)
        brand_cost_rows.append(r)
        r += 1

    # ── ИТОГО ПОРТФЕЛЬ: белая строка жирным. Инверсия к подытогам брендов —
    # итог не спорит с ними за внимание, а закрывает таблицу.
    _put(ws, r, C_NAME, "ИТОГО ПОРТФЕЛЬ", font=_f(10, True), fill=WHITE, align=LEFT, fmt=ACC)
    for i in range(12):
        col = get_column_letter(C_JAN + i)
        f = ",".join(f"{col}{x}" for x in brand_cost_rows)
        _put(ws, r, C_JAN + i, f'=IF(SUM({f})=0,"—",SUM({f}))' if brand_cost_rows else "—",
             font=_f(10, True), fill=WHITE, align=RIGHT, fmt=ACC)
    _sum_row_cell(ws, r, fill=WHITE, bold=True, fmt=ACC)
    ws.row_dimensions[r].height = 27

    # суммы кварталов в шапке — ссылками на строку портфеля
    for q in range(4):
        c1 = C_JAN + q * 3
        rng = f"{get_column_letter(c1)}{r}:{get_column_letter(c1 + 2)}{r}"
        ws.cell(hdr, c1).value = f'=CONCATENATE("{QUARTERS[q]} · ",TEXT(SUM({rng}),"# ##0")," ₽")'
    return r


def _sum_row_cell(ws, r, fill=None, bold=False, color=TEXT, font=None, fmt=ACC):
    a, b = get_column_letter(C_JAN), get_column_letter(C_JAN + 11)
    _put(ws, r, C_TOTAL, f"=SUM({a}{r}:{b}{r})",
         font=font or _f(10, bold, color), fill=fill, align=RIGHT, fmt=fmt)


def _extras_table(ws, r, extras):
    """Разовые услуги под матрицей. Колонки шире матричных, поэтому позиция и
    период растянуты объединением, а не отдельной шириной колонки."""
    _span(ws, r, C_NAME, 11, "ДОПОЛНИТЕЛЬНЫЕ УСЛУГИ (разово, без показов)",
          font=_f(10, True, NAVY_700), fill=GREY_BG, align=LEFT, border=UNDERLINE)
    ws.row_dimensions[r].height = 15
    r += 1
    hdr = _f(10, True, WHITE)
    _put(ws, r, C_NAME, "Источник", font=hdr, fill=HEAD, align=CTR)
    _span(ws, r, 3, 7, "Позиция", font=hdr, fill=HEAD, align=CTR)
    _put(ws, r, 8, "Бренд", font=hdr, fill=HEAD, align=CTR)
    _span(ws, r, 9, 10, "Период", font=hdr, fill=HEAD, align=CTR)
    _put(ws, r, 11, "Стоимость до НДС", font=hdr, fill=HEAD, align=CTR)
    ws.row_dimensions[r].height = 27.6
    for e in extras:
        r += 1
        _put(ws, r, C_NAME, "SIMB-AD", font=_f(10), fill=GREY_BG, align=CTR)
        _span(ws, r, 3, 7, e["name"], font=_f(10), fill=GREY_BG, align=LEFT)
        _put(ws, r, 8, e["brand"], font=_f(10), fill=GREY_BG, align=LEFT)
        _span(ws, r, 9, 10, f"{e['period']} · разово", font=_f(10), fill=GREY_BG, align=CTR)
        _put(ws, r, 11, e["total"], font=_f(10), fill=GREY_BG, align=RIGHT, fmt=MONEY)
    r += 1
    # Объединения строки ИТОГО повторяют шапку, а не сливаются в одну полосу:
    # так колонки таблицы остаются видны до самого низа.
    _put(ws, r, C_NAME, "ИТОГО", font=_f(10, True, NAVY_700), fill=WHITE, align=LEFT)
    _span(ws, r, 3, 7, None, font=_f(10, True, NAVY_700), fill=WHITE, align=LEFT)
    _put(ws, r, 8, None, font=_f(10, True, NAVY_700), fill=WHITE, align=LEFT)
    _span(ws, r, 9, 10, None, font=_f(10, True, NAVY_700), fill=WHITE, align=LEFT)
    _put(ws, r, 11, f"=SUM(K{r - len(extras)}:K{r - 1})" if extras else 0,
         font=_f(10, True, NAVY_700), fill=WHITE, align=RIGHT, fmt=MONEY)
    return r


def _brand_summary(ws, r, brands, months):
    """Сводка по брендам — средний блок верхнего ряда. Возвращает нижнюю строку."""
    # «Объём показов» суммирует ТОЛЬКО услуги с моделью CPM: у фикса и пакетов в этой
    # же ячейке лежат штуки размещений, и сложение их с показами дало бы число, которое
    # ничего не значит.
    hdr = _f(10, True, WHITE)
    # Без верхней рамки: шапка стоит вплотную под толстой чертой заголовка, и
    # пунктир сверху дал бы двойную линию.
    nt = Border(left=_dash, right=_dash, bottom=_dash)
    _put(ws, r, 5, "Бренд", font=hdr, fill=HEAD, align=CTR, border=nt)
    _span(ws, r, 6, 7, "Флайты", font=hdr, fill=HEAD, align=CTR, border=nt)
    _put(ws, r, 8, "Объём показов (CPM)", font=hdr, fill=HEAD, align=CTR, border=nt)
    _put(ws, r, 9, "Стоимость до НДС", font=hdr, fill=HEAD, align=CTR, border=nt)
    _put(ws, r, 10, "Доля", font=hdr, fill=HEAD, align=CTR, border=nt)
    ws.row_dimensions[r].height = 41.4
    first = r + 1
    for b in brands:
        r += 1
        ws.row_dimensions[r].height = 30
        active = sorted({m for s in b["services"] for m in range(12) if s["cost"][m]})
        cost = sum(sum(s["cost"]) for s in b["services"])
        vol = sum(sum(s["vol"]) for s in b["services"] if s.get("is_cpm"))
        _put(ws, r, 5, b["name"], font=_f(10, True), fill=GREY_BG, align=LEFT)
        _span(ws, r, 6, 7, flight_label(active), font=_f(9, color=TEXT_SOFT),
              fill=GREY_BG, align=LEFT)
        _put(ws, r, 8, vol, font=_f(9), fill=GREY_BG, align=RIGHT, fmt=ACC)
        _put(ws, r, 9, cost, font=_f(9, True), fill=GREY_BG, align=RIGHT, fmt=ACC)
        _put(ws, r, 10, None, font=_f(9), fill=GREY_BG, align=RIGHT, fmt=PCT)
    last = r
    for x in range(first, last + 1):
        ws.cell(x, 10).value = (f'=IF(SUM($I${first}:$I${last})=0,"",'
                                f'I{x}/SUM($I${first}:$I${last}))')
    r += 1
    ws.row_dimensions[r].height = 30
    _put(ws, r, 5, "ИТОГО", font=_f(10, True, NAVY_700), fill=WHITE, align=LEFT)
    _span(ws, r, 6, 7, f"{len(months)} мес.", font=_f(9, True, NAVY_700), fill=WHITE, align=RIGHT)
    _put(ws, r, 8, f"=SUM(H{first}:H{last})", font=_f(9, True, NAVY_700), fill=WHITE,
         align=RIGHT, fmt=ACC)
    _put(ws, r, 9, f"=SUM(I{first}:I{last})", font=_f(9, True, NAVY_700), fill=WHITE,
         align=RIGHT, fmt=ACC)
    _put(ws, r, 10, 1, font=_f(9, True, NAVY_700), fill=WHITE, align=RIGHT, fmt=PCT)
    return r


# ── лист «Бриф» ──────────────────────────────────────────────────────────
BRIEF_FIELDS = [("audience", "Аудитория"), ("buys", "Покупают"), ("interests", "Интересы"),
                ("behavior", "Поведение"), ("competitors", "Конкуренты")]


def sheet_brief(ws, plan, data, names):
    """Бриф отдельным листом: у каждого бренда он свой, в общую шапку не помещается.

    Состав полей сведён к тому, что читает клиент: агентство, гео и таргетинги.
    Плательщик, сейлз и аккаунт — внутренние роли, в брифе им места нет.
    """
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 83.1
    ws.column_dimensions["C"].width = 8.9
    _span(ws, 1, 1, 2, f"Брифы по брендам · {plan.year}", font=_f(28, True, NAVY_700),
          fill=GREY_BG, align=LEFT, border=None)
    ws.row_dimensions[1].height = 34.8
    r = 4
    for b in data["brands"]:
        br = b["line"].brief or {}
        tg = br.get("targeting") or {}
        _span(ws, r, 1, 2, b["name"].upper(), font=_f(11, True, NAVY_700), fill=GREY_BG,
              align=LEFT, border=UNDERLINE)
        ws.row_dimensions[r].height = 15
        r += 1
        pairs = [("Агентство", names["agency"].get(br.get("agency_id")) or "—"),
                 ("ГЕО", names["geo"].get(br.get("geo_id")) or "—")]
        pairs += [(label, _join(tg.get(key))) for key, label in BRIEF_FIELDS]
        seas = br.get("seasonality") or []
        if any(seas):
            pairs.append(("Сезонность", ", ".join(
                f"{MONTHS_SHORT[i]} {seas[i]}" for i in range(min(12, len(seas))) if seas[i])))
        if br.get("text"):
            pairs.append(("Комментарий", br["text"]))
        for k, v in pairs:
            _put(ws, r, 1, k, font=_f(10, True), fill=GREY_BG, align=LEFT)
            _put(ws, r, 2, v, font=_f(10), fill=WHITE, align=LEFT)
            r += 1
        r += 1
    # Запас больше, чем на «Сводной»: брифы короткие, и подложка, обрывающаяся сразу
    # под последним блоком, читается как недорисованная, а не как поле.
    _wash(ws, 10, pad=15)


def _join(v):
    if not v:
        return "—"
    if isinstance(v, list):
        vals = [str(x) for x in v if x not in (None, "")]
        return ", ".join(vals) if vals else "—"
    return str(v)


# ── блок «Прогнозные показатели» в шапке ─────────────────────────────────
# Заменяет левую часть шапки шаблона (агентство/период/бриф): всё это есть на листах
# «Бриф» и «Сводная», а на листе с закупкой нужнее итоговая маркетинговая картина.
# Правки владельца сняты с его файла (18.08.2026), оформление воспроизведено оттуда же.
METRICS_CAPTION = "ПРОГНОЗНЫЕ ПОКАЗАТЕЛИ"
# ARGB строго с альфой FF: "002060" openpyxl запишет как 00002060 — полностью прозрачный,
# и тёмно-синяя шапка блока пропадёт.
METRICS_HEAD_BG, METRICS_HEAD_FG = "FF002060", "FFFFFF"
# Подложка листа — тема 0 с затемнением. Красится по ВСЕЙ области блока, а не по занятым
# ячейкам: колонки G и H в пустых слотах оставались белыми проплешинами на общем фоне.
WASH_THEME, WASH_TINT = 0, -0.05
METRICS_ROW_H = 26.4
METRICS_SLOTS = 5          # строк под бренды без сдвига медиаплана
METRICS_TOP = 9            # строка заголовка блока
METRICS_FIRST = 12         # первая строка бренда
METRICS_LAST_COL = 8       # H — правее начинается блок «ИТОГО» шаблона
# (поле, подпись, формат). Пустая подпись — колонка занята соседней (D объединена с E).
METRICS_COLS = [("_brand", "Бренд", "@"),
                ("gross", "Итоговая стоимость с НДС", "#,##0.00"),
                ("revenue", "Доход руб.", "#,##0"),
                ("roi", "ROI", "0%"),
                ("cpo", "CPO", "#,##0"),
                ("cpm", "CPM", "#,##0")]


def metrics_extra_rows(n_brands: int) -> int:
    """Сколько строк добавить под блок, чтобы отступ до медиаплана не съело.

    Вставлять их надо ДО отрисовки таблицы: openpyxl не правит формулы при вставке
    строк, и сдвиг после рендера порвал бы все ссылки размещений."""
    return max(0, n_brands - METRICS_SLOTS)


def sheet_metrics(ws, groups, cols):
    """Нарисовать блок показателей: строка на бренд, значения — формулы по его строкам.

    `groups` — [(имя, первая_строка_данных, последняя)], `cols` — карта поле→колонка
    отрисованной таблицы. Показы и чеки в подытоге бренда не суммируются, поэтому CPO
    и CPM считаются прямо по диапазону строк бренда — так блок не зависит от того,
    какие колонки шаблон кладёт в строку «Итого».
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.styles.colors import Color

    dash = Side(style="dashed", color="BFBFBF")
    dot = Side(style="dotted", color="BFBFBF")
    box = Border(left=dash, right=dash, top=dash, bottom=dash)
    head_box = Border(left=dot, right=dot, bottom=dot)
    head_fill = PatternFill("solid", fgColor=METRICS_HEAD_BG)
    wash = PatternFill("solid", fgColor=Color(theme=WASH_THEME, tint=WASH_TINT))

    last = METRICS_FIRST + max(len(groups), METRICS_SLOTS) - 1
    # Старая шапка (агентство, период, бриф) вычищается целиком, вместе с её
    # объединениями: наложить новые поверх пересекающихся Excel считает поломкой файла.
    for mr in list(ws.merged_cells.ranges):
        if mr.min_row <= last and mr.max_row >= METRICS_TOP and mr.min_col <= 14:
            ws.unmerge_cells(str(mr))
    # Чистится и красится ВСЯ область старой шапки (B..N), а не только колонки блока:
    # под таргетинги шаблон отводил белые поля до колонки N, и покраска до H оставляла
    # справа от CPM белый прямоугольник на сером фоне.
    for r in range(METRICS_TOP, last + 1):
        for c in range(2, 15):
            cell = ws.cell(r, c)
            cell.value = None
            cell.border = Border()
            cell.fill = wash

    ws.merge_cells(start_row=METRICS_TOP, end_row=METRICS_TOP + 1,
                   start_column=2, end_column=METRICS_LAST_COL)
    cap = ws.cell(METRICS_TOP, 2)
    cap.value = METRICS_CAPTION
    cap.font = Font(name="Calibri", size=12, bold=True)
    cap.alignment = Alignment(horizontal="left", vertical="center")
    cap.border = Border(bottom=Side(style="medium"))

    hdr = METRICS_TOP + 2
    ws.row_dimensions[hdr].height = METRICS_ROW_H
    for i, (_f, label, _fmt) in enumerate(METRICS_COLS):
        cell = ws.cell(hdr, 2 + i + (1 if i >= 3 else 0))   # D объединена с E → сдвиг
        cell.value = label
        cell.font = Font(name="Calibri", size=10, bold=True, color=METRICS_HEAD_FG)
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = head_box
    ws.merge_cells(start_row=hdr, end_row=hdr, start_column=4, end_column=5)

    def rng(field, a, b):
        col = cols.get(field)
        return f"SUM({col}{a}:{col}{b})" if col else "0"

    for i, (name, a, b) in enumerate(groups):
        R = METRICS_FIRST + i
        ws.row_dimensions[R].height = METRICS_ROW_H
        gross, rev = f"C{R}", f"D{R}"
        vals = [name.upper(),
                f"={rng('gross', a, b)}",
                f"={rng('revenue', a, b)}",
                # ROI и CPO/CPM повторяют формулы строк таблицы: ROI считается от
                # стоимости С НДС, CPO и CPM — от стоимости ДО НДС. Иначе шапка и
                # таблица давали бы по одному бренду два разных числа.
                f'=IF({gross}>0,({rev}-{gross})/{gross},"")',
                f'=IF({rng("checks", a, b)}>0,{rng("net", a, b)}/{rng("checks", a, b)},"")',
                f'=IF({rng("imp", a, b)}>0,{rng("net", a, b)}/{rng("imp", a, b)}*1000,"")']
        for j, ((_f, _l, fmt), v) in enumerate(zip(METRICS_COLS, vals)):
            c = 2 + j + (1 if j >= 3 else 0)
            cell = ws.cell(R, c)
            cell.value = v
            cell.font = Font(name="Calibri", size=12)
            cell.alignment = Alignment(horizontal="left" if j == 0 else "center",
                                       vertical="center", wrap_text=True)
            cell.number_format = fmt
            # Рамки как в правленом файле владельца: денежная часть пунктиром-тире,
            # ROI без правой грани (её рисует левая грань CPO), CPO и CPM — точками.
            cell.border = (Border(left=dash, top=dash, bottom=dash) if j == 3
                           else Border(left=dot, right=dot, top=dot, bottom=dot) if j >= 4
                           else box)
            if j == 2:
                ws.merge_cells(start_row=R, end_row=R, start_column=4, end_column=5)


# ── лист «Годовой МП» ────────────────────────────────────────────────────
# Подытог отбивается заливкой, а не полосой: в нём есть числа, и объединять строку
# нельзя. Месяц светлее бренда — вложенность видна без отступов.
SUB_MONTH_FILL, SUB_BRAND_FILL = "EDF0F7", "DFE4F0"


def year_rows(lines, svc, add, names) -> tuple:
    """Строки листа «Годовой МП»: бренд → месяц, с подытогами обоих уровней.

    Порядок бренд→месяц выбран владельцем: лист читается как история каждого бренда за
    год. Общая картина месяца остаётся на «Сводной» и на месячных вкладках.

    Месяц НЕ отбивается ни полосой, ни подытогом: у строки есть колонка «Период» с
    `2026-04`, и этого достаточно — поперечные ряды только рвали список. Поэтому же
    период проставляется в саму строку: в шапке листа стоит год, и без этого все
    двенадцать месяцев выглядели бы одинаково.

    Возвращает (rows, extras) в формате, который принимает media_plans.render_mp_sheet:
    служебные элементы — {"_band": …} и {"_subtotal": …, "_kind": "brand"}.
    """
    rows, extras = [], []
    for line in lines:
        brand = names["brand"].get(line.brand_id) or "Без бренда"
        chunk, ex_chunk = [], []
        for m in range(12):
            items = month_items(line, m)
            if not items:
                continue
            r, e = _parts(line, m, svc, add, items)
            period = f"{line.year}-{m + 1:02d}"
            for row in r:
                row["period"] = period
            chunk.extend(r)
            ex_chunk.extend(e)
        if chunk:
            rows.append({"_band": brand.upper()})
            rows.extend(chunk)
            rows.append({"_subtotal": f"Итого · {brand} за год", "_kind": "brand"})
        if ex_chunk:
            extras.append({"_band": brand.upper()})
            extras.extend(ex_chunk)
    return rows, extras


def brand_groups(specials, first, last) -> list:
    """[(бренд, первая_строка_данных, последняя)] по полосам-разделителям.

    Границы берутся из тех же служебных строк, что и подытоги: данные бренда идут от
    его полосы до следующей служебной строки. Работает и на месячном листе, где
    подытогов нет вовсе, — там полоса просто упирается в следующую полосу."""
    marks = sorted(specials, key=lambda x: x[0])
    out = []
    for i, (R, it) in enumerate(marks):
        if not it.get("_band"):
            continue
        end = marks[i + 1][0] - 1 if i + 1 < len(marks) else last
        if end >= R + 1:
            out.append((it["_band"], R + 1, end))
    return out


def collecting_hook(sink):
    """Хук рендера: запомнить диапазоны брендов и проставить подытоги."""
    def hook(ws, cols, tcol, first, last, specials):
        sink.append((cols, brand_groups(specials, first, last)))
        return year_row_hook(ws, cols, tcol, first, last, specials)
    return hook


def year_row_hook(ws, cols, tcol, first, last, specials):
    """Проставить формулы подытогов и вернуть строки, по которым считается ИТОГО.

    Границы групп выводятся из самих служебных строк, а не из отдельной разметки:
    подытог суммирует всё от предыдущей служебной строки до себя. Если внутри уже есть
    подытоги уровнем ниже, складываются ОНИ, а не данные — иначе месяц вошёл бы в бренд
    дважды. Сейчас уровень один (бренд), но каскад оставлен: месячные подытоги убирали
    уже после того, как он был написан, и вернуть их — это снова одна строка.

    ИТОГО суммирует подытоги брендов, а не диапазон блока: подытоги лежат ВНУТРИ него,
    и `=СУММ(первая:последняя)` удвоил бы годовой бюджет правдоподобным числом.
    """
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import column_index_from_string
    from app.routers.media_plans import subtotal_formulas

    month_rows, brand_rows = [], []
    prev = first - 1                     # конец предыдущей служебной строки
    pending_months = []                  # подытоги месяцев текущего бренда
    for R, it in sorted(specials, key=lambda x: x[0]):
        if it.get("_subtotal"):
            kind = it.get("_kind")
            own = [(prev + 1, R - 1)] if R - 1 >= prev + 1 else []
            if kind == "month":
                ranges = own
                pending_months.append(R)
                month_rows.append(R)
            else:
                # Есть подытоги месяцев — складываем их; нет — сами строки бренда.
                ranges = list(pending_months) or own
                pending_months = []
                brand_rows.append(R)
            if ranges:
                for col, f in subtotal_formulas(cols, tcol, ranges).items():
                    ws[f"{col}{R}"] = f
            # Подпись — в самую левую колонку, которая НЕ суммируется: иначе она
            # затрёт только что проставленную формулу, и подытог молча станет текстом.
            summed = set(tcol.values()) | {cols[f] for f in tcol if f in cols}
            free = [c for c in cols.values() if c not in summed]
            label_col = min(column_index_from_string(c)
                            for c in (free or list(cols.values())))
            ws.cell(R, label_col).value = it["_subtotal"]
        prev = R
    # Оформление — после заливки формул, иначе _sub_cell затрёт стиль.
    idx = [column_index_from_string(c) for c in cols.values()]
    c1, c2 = min(idx), max(idx)
    for R in month_rows + brand_rows:
        fill = PatternFill("solid", fgColor=SUB_BRAND_FILL if R in brand_rows else SUB_MONTH_FILL)
        for c in range(c1, c2 + 1):
            cell = ws.cell(R, c)
            cell.fill = fill
            cell.font = Font(name="Arial", size=10, bold=True, color=NAVY_700)
    return brand_rows or month_rows or None


# ── сборка книги ─────────────────────────────────────────────────────────
# Скидка заметна глазом, а не только в цифре: у доп. услуг режимы 50 % и «бонус»
# дают 50 и 100 — по зелёным клеткам сразу видно, что отдано бесплатно.
DISCOUNT_HEADER = "Скидка,%"
DISCOUNT_FILL = "FFE2F4E4"


def highlight_discounts(ws) -> int:
    """Подсветить клетки со скидкой в обеих таблицах листа. Возвращает число клеток."""
    from openpyxl.styles import PatternFill

    green = PatternFill("solid", fgColor=DISCOUNT_FILL)
    cols = {c for r in range(1, ws.max_row + 1) for c in range(1, ws.max_column + 1)
            if ws.cell(r, c).value == DISCOUNT_HEADER}
    n = 0
    for c in cols:
        for r in range(1, ws.max_row + 1):
            v = ws.cell(r, c).value
            # Только заполненные ставкой клетки: строки-итоги скидку не несут, а
            # формулы (строка «Скидка,руб») сюда не попадают — там не число.
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                ws.cell(r, c).fill = green
                n += 1
    return n


def _render_with_metrics(ws, full, rows, extras):
    """Отрисовать лист закупки и заменить левую часть шапки блоком показателей.

    Строки под лишние бренды вставляются ДО рендера: openpyxl не правит формулы при
    вставке, и сдвиг после отрисовки порвал бы все ссылки таблицы."""
    from app.routers.media_plans import render_mp_sheet

    n = sum(1 for it in rows if isinstance(it, dict) and it.get("_band"))
    extra = metrics_extra_rows(n)
    if extra:
        ws.insert_rows(METRICS_FIRST + METRICS_SLOTS, extra)
    sink = []
    render_mp_sheet(ws, full, rows, extras, row_hook=collecting_hook(sink))
    if sink:
        cols, groups = sink[0]
        sheet_metrics(ws, groups, cols)
    highlight_discounts(ws)
    return ws


def build_workbook(db, plan, lines, svc, add, names, template_path, vat_rate):
    from openpyxl import load_workbook

    data = collect(db, lines, svc, add, names)
    wb = load_workbook(template_path)
    tpl = wb["МП"] if "МП" in wb.sheetnames else wb.active

    adv = names["adv"].get(plan.advertiser_id) or "—"
    b0 = (lines[0].brief or {}) if lines else {}

    def head(period, subtitle):
        """Шапка листа годовой выгрузки: общая часть брифа, остальное — на «Брифе»."""
        return {
            "period": period, "advertiser": adv,
            "brand": f"Брендов: {len(data['brands'])}",
            "agency": names["agency"].get(b0.get("agency_id")) or "—",
            "geo": names["geo"].get(b0.get("geo_id")) or "—",
            "title": plan.title or f"Годовой план {plan.year}",
            # Таргетинги в шапку не идут: у каждого бренда свой бриф, общей строки не
            # существует. Они на листе «Бриф».
            "targeting": {}, "created_at": None, "date_from": None, "date_to": None,
            "head_override": {
                "mp_title": f"Медиаплан · {adv} · {period}",
                "mp_subtitle": subtitle,
                "tg_audience": "см. лист «Бриф»", "tg_buys": "см. лист «Бриф»",
                "tg_interests": "см. лист «Бриф»", "tg_behavior": "см. лист «Бриф»",
                "tg_competitors": "см. лист «Бриф»",
            },
        }

    # Лист «Годовой МП» — весь год одним списком в макете месячного МП.
    yrows, yextras = year_rows(lines, svc, add, names)
    year_ws = None
    if yrows:
        year_ws = wb.copy_worksheet(tpl)
        year_ws.title = "Годовой МП"
        _render_with_metrics(year_ws,
                             head(str(plan.year),
                                  f"SIMB-AD · {plan.year} · брендов: {len(data['brands'])} · "
                                  f"месяцев с закупкой: {len(data['months'])} · "
                                  f"таргетинги — на листе «Бриф»"),
                             yrows, yextras)

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
        full = head(period, f"SIMB-AD · {period} · брендов: {len(data['brands'])} · "
                            f"таргетинги — на листе «Бриф»")
        ws = wb.copy_worksheet(tpl)
        ws.title = period
        _render_with_metrics(ws, full, rows, extras)

    wb.remove(tpl)
    summary = wb.create_sheet("Сводная")
    brief = wb.create_sheet("Бриф")
    sheet_summary(summary, plan, data, names, vat_rate)
    sheet_brief(brief, plan, data, names)
    # Порядок: Сводная → Бриф → Годовой МП → месяцы (создавались вразнобой, переставляем).
    head_sheets = [s for s in (summary, brief, year_ws) if s is not None]
    wb._sheets = head_sheets + [s for s in wb._sheets if s not in head_sheets]
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:
        pass
    return wb, data
