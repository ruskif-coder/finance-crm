# -*- coding: utf-8 -*-
"""Приложение к договору в .docx — редактируемый близнец печатной формы.

Зачем оба формата: PDF уходит на подпись, а .docx — юристу клиента, который вносит
правки перед подписанием. Из PDF этого не сделать.

**Оба документа собираются из ОДНОГО словаря** `annex.build(...)`: суммы, падежи, стороны
и строки медиаплана считаются один раз на сервере. Разные форматы одного документа с
разными числами — самая дорогая из возможных здесь ошибок, и защита от неё в том, что
считать тут нечего.

Вёрстка повторяет подписанный образец: альбомная A4, Times New Roman, синяя шапка таблицы
с белыми рамками, строка ИТОГО заливкой, пункты 1 / 1.1 / 1.2 / 2 / 3 с висячим номером.
"""
from io import BytesIO
from typing import Optional

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

FONT = "Times New Roman"
HEADER_FILL = "4472C4"      # синяя шапка — как в образце и в наших выгрузках медиаплана
TOTAL_FILL = "D9E2F3"
BORDER = "FFFFFF"           # рамки белые (решение владельца 05.09.2026)

COLS = ["Место\nразмещения", "Позиция", "Гео", "Формат", "Девайс",
        "Тип ротации\n(для медийных\nформатов)", "Модель\nзакупки", "Объем размещения",
        "Период", "Стоимость\nза единицу\nзакупки", "Стоимость\nразмещения",
        "НДС {rate}%", "Стоимость\nразмещения\nс учетом НДС"]

# Доли колонок, а не сантиметры. Числа в сантиметрах уже разошлись с полосой набора:
# python-docx создаёт документ размером Letter (27,9 × 21,6), а не A4, и таблица на
# 27,7 см выехала за правое поле — в Word это видно сразу, а в коде не видно вовсе.
# Поэтому размер страницы задаётся явно, а ширины считаются ОТ ПОЛОСЫ: поменяются поля
# или формат — таблица останется внутри.
# Доли подобраны по САМОМУ ДЛИННОМУ содержимому колонки, а не по длине заголовка.
# Денежные считаны из «12 345 678,90»: тринадцать знаков кеглем 7,5 pt Times — это
# ~1,7 см плюс поля ячейки. Замер 05.09.2026: НДС при доле 1,5 давал 1,44 см, и
# «90 163,97» переносилось ПОСЛЕ ЗАПЯТОЙ (разряды и так неразрывные) — на бумаге это
# читается как другое число. Сумма долей равна полосе, поэтому доля = сантиметры.
WEIGHTS = [1.8, 3.5, 1.1, 1.5, 1.8, 2.0, 1.6, 2.2, 2.3, 1.9, 2.3, 2.2, 2.3]

PAGE_W, PAGE_H = 29.7, 21.0          # A4, альбомная
MARGIN_X, MARGIN_Y = 1.6, 1.5
USABLE = PAGE_W - 2 * MARGIN_X       # полоса набора, см


def _widths(usable: float = USABLE) -> list:
    k = usable / sum(WEIGHTS)
    return [w * k for w in WEIGHTS]

_fix2 = lambda v: ("" if v is None else f"{float(v):,.2f}"          # noqa: E731
                   .replace(",", " ").replace(".", ","))
_int = lambda v: ("" if v is None else f"{int(v):,}".replace(",", " "))  # noqa: E731
_dm = lambda d: (d.strftime("%d.%m.%Y") if d else "")                # noqa: E731

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]


def _nb(text) -> str:
    """Строка, которую нельзя разорвать переносом: пробелы неразрывные, дефис тоже.

    Номер договора «РМ 30-11-2023» Word ломает и по пробелу, и по дефису — получается
    «№ РМ 30-11-» на одной строке и «2023» на следующей, то есть на вид два разных
    номера. В печатной форме это закрыто `white-space: nowrap`; здесь — самими символами,
    потому что своего «nowrap» у абзаца Word нет.
    """
    return (str(text or "").replace(" ", " ").replace("-", "‑"))


def _long_date(d) -> str:
    """«31» мая 2026 г. — как в подписанном документе, а не 31.05.2026."""
    return f"«{d.day:02d}» {MONTHS[d.month - 1]} {d.year} г." if d else "«__» ______ ____ г."


def _shade(cell, fill: str) -> None:
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(el)


def _fixed_layout(table) -> None:
    """Фиксированная разметка. Без неё Word пересчитывает ширины по содержимому и
    выносит числовые колонки за поле, сколько бы мы им ни назначили."""
    el = OxmlElement("w:tblLayout")
    el.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(el)


def _borders(table) -> None:
    """Рамки таблицы. python-docx их не умеет — только через XML свойств таблицы."""
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:color"), BORDER)
        borders.append(el)
    table._tbl.tblPr.append(borders)


def _run(p, text: str, *, bold=False, italic=False, size=11.5, color=None):
    r = p.add_run(text)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    # Кириллица в Word берёт шрифт из отдельного свойства: без него текст съезжает на
    # шрифт по умолчанию, и документ выглядит собранным из двух гарнитур.
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    r._element.rPr.rFonts.set(qn("w:cs"), FONT)
    return r


def _cell_text(cell, text: str, *, bold=False, italic=False, size=7.5, align="center"):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = {"center": WD_ALIGN_PARAGRAPH.CENTER,
                   "left": WD_ALIGN_PARAGRAPH.LEFT,
                   "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    for i, line in enumerate(str(text).split("\n")):
        if i:
            p.add_run().add_break()
        _run(p, line, bold=bold, italic=italic, size=size,
             color="FFFFFF" if cell._tc.find(qn("w:tcPr")) is not None and bold and
             size <= 7 else None)


def _clause(doc, number: str, text: str, *, indent=0.0):
    """Пункт с висячим номером: номер слева, текст выровнен по общей линии, влево."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(1.2 + indent)
    pf.first_line_indent = Cm(-1.2)
    pf.space_after = Pt(6)
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _run(p, f"{number}\t")
    _run(p, text)
    return p


def _party_line(p: Optional[dict], role: str) -> str:
    if not p or not p.get("name"):
        return f"___________, именуемое в дальнейшем «{role}»"
    pos = p.get("position_gen") or p.get("position") or "___________"
    fio = p.get("director_gen") or p.get("director") or "___________"
    basis = p.get("basis_gen") or p.get("basis") or "___________"
    acting = p.get("acting") or "действующего"
    return (f"{p['name']}, именуемое в дальнейшем «{role}», в лице {pos} {fio}, "
            f"{acting} на основании {basis}")


def build_docx(d: dict) -> bytes:
    """Собрать .docx из того же словаря, что печатает PDF."""
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    # Размер задаётся ЧИСЛАМИ, а не переворотом умолчания: умолчание у python-docx —
    # Letter, и «перевернули страницу» дало бы 27,9 см вместо 29,7.
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.top_margin = sec.bottom_margin = Cm(MARGIN_Y)
    sec.left_margin = sec.right_margin = Cm(MARGIN_X)

    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(11.5)
    style.paragraph_format.space_after = Pt(0)

    cust, ex = d.get("customer") or {}, d.get("executor") or {}
    contract = d.get("contract") or {}

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(h, d.get("number") or "Приложение", bold=True, size=12)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(12)
    _run(sub, f"к Договору {_nb('№ ' + (contract.get('number') or '________'))} "
              f"об оказании услуг от {_long_date(contract.get('date'))}")

    # Место слева, дата справа — одной строкой через табуляцию по правому краю полосы.
    row = doc.add_paragraph()
    row.paragraph_format.space_after = Pt(12)
    row.paragraph_format.tab_stops.add_tab_stop(Cm(USABLE), WD_ALIGN_PARAGRAPH.RIGHT)
    _run(row, f"{d.get('signed_place') or 'г. Москва'}\t{_long_date(d.get('date'))}")

    pre = doc.add_paragraph()
    pre.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pre.paragraph_format.space_after = Pt(10)
    _run(pre, f"{_party_line(cust, 'Заказчик')}, с одной стороны, и "
              f"{_party_line(ex, 'Исполнитель')}, с другой стороны, заключили настоящее "
              f"{d.get('number') or 'Приложение'} к Договору "
              f"{_nb('№ ' + (contract.get('number') or '________'))} об оказании услуг "
              f"от {_long_date(contract.get('date'))} (далее по тексту – «Договор») "
              f"о нижеследующем:")

    _clause(doc, "1.", d.get("body") or "")
    _table(doc, d)
    _clause(doc, "1.1.", _clause_11(d), indent=0.8)
    _clause(doc, "1.2.", CLAUSE_12, indent=0.8)
    _clause(doc, "2.", CLAUSE_2)
    _clause(doc, "3.", _clause_3(d))

    sign = doc.add_paragraph()
    sign.paragraph_format.space_before = Pt(14)
    sign.paragraph_format.space_after = Pt(8)
    _run(sign, "Подписи Сторон:", bold=True)
    _signatures(doc, ex, cust)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


CLAUSE_12 = ("Услуги оказываются в соответствии с требованиями Заказчика. Стороны вправе "
             "согласовывать требования к Услугам, предоставлять и получать исходные "
             "материалы, необходимые для оказания Услуг. Любое изменение условий "
             "настоящего Приложения согласовывается сторонами отдельными Приложениями "
             "к Договору.")

CLAUSE_2 = ("В случае если Заказчик недоволен оказанными Услугами, он мотивированно "
            "сообщает Исполнителю, что его не устраивает в конкретной Услуге, и "
            "Исполнитель, согласовав с Заказчиком сроки на выполнение данных исправлений, "
            "приступает к доработке.")


def _clause_11(d: dict) -> str:
    return (f"Общая стоимость Услуг Исполнителя по настоящему Приложению составляет сумму "
            f"в размере {d.get('amount_words') or ''}, в том числе НДС "
            f"{d.get('vat_rate')}% — {d.get('vat_words') or ''}. Оплата услуг Исполнителя "
            f"по настоящему Приложению осуществляется Заказчиком на основании "
            f"выставленного счета, счет-фактуры, Акта оказания услуг согласно разделу 4 "
            f"Договора.")


def _clause_3(d: dict) -> str:
    return (f"Во всем остальном, не урегулированном настоящим Приложением, стороны "
            f"руководствуются положениями Договора. Настоящее Приложение вступает в силу "
            f"с момента его подписания Сторонами и распространяет свое действие на "
            f"отношения Сторон, возникшие с {_dm(d.get('period_from'))} г. Настоящее "
            f"Приложение составлено в 2 (двух) экземплярах, имеющих равную юридическую "
            f"силу, по одному для каждой из Сторон, и является неотъемлемой частью "
            f"Договора.")


def _table(doc, d: dict) -> None:
    rows = d.get("rows") or []
    if not rows:
        return
    widths = _widths()
    t = doc.add_table(rows=1, cols=len(COLS))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _fixed_layout(t)
    _borders(t)
    for col, w in zip(t.columns, widths):
        col.width = Cm(w)

    for i, (cell, title) in enumerate(zip(t.rows[0].cells, COLS)):
        _shade(cell, HEADER_FILL)
        cell.width = Cm(widths[i])
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        for j, line in enumerate(title.format(rate=d.get("vat_rate")).split("\n")):
            if j:
                p.add_run().add_break()
            _run(p, line, bold=True, size=7, color="FFFFFF")

    total = {"volume": 0.0, "net": 0.0, "vat": 0.0, "gross": 0.0}
    for r in rows:
        cells = t.add_row().cells
        for i, w in enumerate(widths):
            cells[i].width = Cm(w)
        period = f"{_dm(r.get('date_from') or d.get('period_from'))} –\n" \
                 f"{_dm(r.get('date_to') or d.get('period_to'))}"
        _cell_text(cells[0], r.get("network") or "—", bold=True)
        _cell_text(cells[1], r.get("doc_position") or r.get("position") or "—",
                   italic=True, align="left")
        _cell_text(cells[2], r.get("geo") or "—")
        _cell_text(cells[3], r.get("format") or "—")
        _cell_text(cells[4], r.get("device") or "—")
        _cell_text(cells[5], r.get("rotation") or "—")
        _cell_text(cells[6], r.get("model") or "—")
        _cell_text(cells[7], _int(r.get("volume")) or "—", align="right")
        _cell_text(cells[8], period)
        _cell_text(cells[9], _fix2(r.get("unit_price")), align="right")
        _cell_text(cells[10], _fix2(r.get("amount")), bold=True, align="right")
        _cell_text(cells[11], _fix2(r.get("vat")), align="right")
        _cell_text(cells[12], _fix2(r.get("gross")), bold=True, align="right")
        total["volume"] += float(r.get("volume") or 0)
        total["net"] += float(r.get("amount") or 0)
        total["vat"] += float(r.get("vat") or 0)
        total["gross"] += float(r.get("gross") or 0)

    # ИТОГО считается по СТРОКАМ ТАБЛИЦЫ, а не берётся из шапки документа: колонка и её
    # итог обязаны сходиться на бумаге, иначе расхождение заметит подписант.
    cells = t.add_row().cells
    for i, w in enumerate(widths):
        cells[i].width = Cm(w)
        _shade(cells[i], TOTAL_FILL)
    cells[0].merge(cells[6])
    _cell_text(cells[0], "ИТОГО:", bold=True, align="right")
    _cell_text(cells[7], _int(total["volume"]), bold=True, align="right")
    _cell_text(cells[10], _fix2(total["net"]), bold=True, align="right")
    _cell_text(cells[11], _fix2(total["vat"]), bold=True, align="right")
    _cell_text(cells[12], _fix2(total["gross"]), bold=True, align="right")
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def _signatures(doc, ex: dict, cust: dict) -> None:
    """Стороны по противоположным краям листа — таблицей без рамок: в Word это
    единственный способ удержать две колонки, которые не разъезжаются при правке."""
    t = doc.add_table(rows=1, cols=2)
    t.autofit = False
    for cell, party, align in ((t.rows[0].cells[0], ex, "left"),
                               (t.rows[0].cells[1], cust, "right")):
        cell.width = Cm(USABLE / 2)
        cell.text = ""
        a = {"left": WD_ALIGN_PARAGRAPH.LEFT, "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
        head = cell.paragraphs[0]
        head.alignment = a
        _run(head, "Исполнитель:" if party is ex else "Заказчик:", bold=True)
        for text in (party.get("name") or "—",
                     party.get("position") or "____________",
                     "",
                     f"____________________ /{party.get('short_fio') or '_________'}/",
                     "М.П."):
            p = cell.add_paragraph()
            p.alignment = a
            _run(p, text)
