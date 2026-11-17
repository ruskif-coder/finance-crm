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

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.annex_tpl import doc_kind as DK
from app.annex_tpl.party import party_line as _party_line

FONT = "Times New Roman"
HEADER_FILL = "4472C4"      # синяя шапка — как в образце и в наших выгрузках медиаплана
TOTAL_FILL = "D9E2F3"
BORDER = "000000"           # рамки чёрные (владелец 21.10.2026, просьба бухгалтерии; до того — белые, решение 05.09.2026)

PAGE_W, PAGE_H = 29.7, 21.0          # A4, альбомная
MARGIN_X, MARGIN_Y = 1.6, 1.5
USABLE = PAGE_W - 2 * MARGIN_X       # полоса набора, см (размер страницы явно: python-docx по умолчанию даёт Letter)

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


def _basis_page(doc, d: dict) -> None:
    """Страница «Основание для закрывающих документов» — после ДС, одним файлом: клиент видит, что будет написано в УПД и счёте, и подтверждает."""
    doc.add_page_break()
    h = doc.add_paragraph()
    h.paragraph_format.space_after = Pt(8)
    _run(h, "Основание для закрывающих документов", bold=True, size=12)
    note = doc.add_paragraph()
    note.paragraph_format.space_after = Pt(10)
    _run(note, f"К {DK.to_dative(d.get('number'), _kind(d))} к Договору {_nb('№ ' + ((d.get('contract') or {}).get('number') or '________'))}. "
               "Формулировка, которая будет указана в УПД и счёте. Просим согласовать.", italic=True, size=10.5)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _run(p, d.get("closing_basis") or "")


def build_docx(d: dict, with_basis: bool = False) -> bytes:
    """Собрать .docx из того же словаря, что печатает PDF. `with_basis` — добавить страницу с основанием закрывающих документов."""
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    # Размер задаётся ЧИСЛАМИ, а не переворотом умолчания: умолчание у python-docx —
    # Letter, и «перевернули страницу» дало бы 27,9 см вместо 29,7.
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.top_margin = sec.bottom_margin = Cm(MARGIN_Y)
    sec.left_margin = sec.right_margin = Cm(MARGIN_X)
    if d.get("master_code"):              # код мастер-сделки в нижнем колонтитуле каждой страницы
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(fp, d["master_code"], size=8, color="595959")

    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(11.5)
    style.paragraph_format.space_after = Pt(0)

    cust, ex = d.get("customer") or {}, d.get("executor") or {}
    contract = d.get("contract") or {}

    # Заголовок: правленый в конструкторе ДС (05.11.2026) — первая строка жирным, остальные под ней; иначе — как всегда.
    head = [x for x in (d.get("head_text") or "").split("\n") if x.strip()]
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(h, head[0] if head else (d.get("number") or DK.forms(_kind(d))["nom"]), bold=True, size=12)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(12)
    _run(sub, "\n".join(head[1:]) if head else (f"к Договору {_nb('№ ' + (contract.get('number') or '________'))} "
                                                f"об оказании услуг от {_long_date(contract.get('date'))}"))

    # Место слева, дата справа — одной строкой через табуляцию по правому краю полосы.
    row = doc.add_paragraph()
    row.paragraph_format.space_after = Pt(12)
    row.paragraph_format.tab_stops.add_tab_stop(Cm(USABLE), WD_ALIGN_PARAGRAPH.RIGHT)
    if d.get("place_text"):                  # правленое «место и дата»: «|» делит на левую и правую часть
        left, _, right = d["place_text"].partition("|")
        _run(row, f"{left.strip()}\t{right.strip()}" if right.strip() else left.strip())
    else:
        _run(row, f"{d.get('signed_place') or 'г. Москва'}\t{_long_date(d.get('date'))}")

    pre = doc.add_paragraph()
    pre.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pre.paragraph_format.space_after = Pt(10)
    if d.get("preamble"):                    # преамбула — текст шаблона (02.11.2026); без него — прежняя формула
        _run(pre, d["preamble"])
    else:
        _run(pre, f"{_party_line(cust, 'Заказчик')}, с одной стороны, и "
                  f"{_party_line(ex, 'Исполнитель')}, с другой стороны, заключили настоящее "
                  f"{d.get('number') or DK.forms(_kind(d))['nom']} к Договору "
                  f"{_nb('№ ' + (contract.get('number') or '________'))} об оказании услуг "
                  f"от {_long_date(contract.get('date'))} (далее по тексту – «Договор») "
                  f"о нижеследующем:")

    if d.get("clauses"):
        _constructor_body(doc, d, ex, cust)
    else:
        _legacy_body(doc, d, ex, cust)
    if with_basis and d.get("closing_basis"):
        _basis_page(doc, d)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _sign_block(doc, ex: dict, cust: dict, heading: bool = True) -> None:
    """`heading=False` — заголовок уже стоит пунктом шаблона (`document.clauses_of`), второй не печатаем."""
    sign = doc.add_paragraph()
    sign.paragraph_format.space_before = Pt(14)
    sign.paragraph_format.space_after = Pt(8)
    if heading:
        _run(sign, "Подписи Сторон:", bold=True)
    _signatures(doc, ex, cust)


def _constructor_body(doc, d: dict, ex: dict, cust: dict) -> None:
    """Пункты — ровно блоки конструктора, в его порядке (владелец 02.11.2026). Шапку, место и преамбулу файл уже напечатал;
    таблица и подписи встают туда, где их поставил шаблон. Подписи, которых шаблон не поставил, — в конце: без них документ
    не подписать."""
    signed = False
    for c in d["clauses"]:
        if c.get("sys") == "table":
            _table(doc, d)
        elif c.get("sys") == "sign":
            _sign_block(doc, ex, cust, heading=c.get("heading", True))
            signed = True
        elif not c.get("sys"):
            _clause(doc, c.get("num") or "", c.get("text") or "", indent=0.8 if c.get("sub") else 0.0)
    if not signed:
        _sign_block(doc, ex, cust)


def _legacy_body(doc, d: dict, ex: dict, cust: dict) -> None:
    """ДС, собранный до конструктора (модели нет): прежний текст, зашитый в код."""
    _clause(doc, "1.", d.get("body") or "")
    _table(doc, d)
    _clause(doc, "1.1.", _clause_11(d), indent=0.8)
    _clause(doc, "1.2.", _w(d, CLAUSE_12), indent=0.8)
    _clause(doc, "2.", CLAUSE_2)
    _clause(doc, "3.", _clause_3(d))
    _sign_block(doc, ex, cust)


CLAUSE_12 = ("Услуги оказываются в соответствии с требованиями Заказчика. Стороны вправе "
             "согласовывать требования к Услугам, предоставлять и получать исходные "
             "материалы, необходимые для оказания Услуг. Любое изменение условий "
             "настоящего Приложения согласовывается сторонами отдельными Приложениями "
             "к Договору.")

CLAUSE_2 = ("В случае если Заказчик недоволен оказанными Услугами, он мотивированно "
            "сообщает Исполнителю, что его не устраивает в конкретной Услуге, и "
            "Исполнитель, согласовав с Заказчиком сроки на выполнение данных исправлений, "
            "приступает к доработке.")


def _kind(d: dict) -> str:
    """Вид документа для файла. `kind` приходит из модели сборки; у документов, замороженных до
    31.10.2026, его в модели нет — тогда мастер-сделка всё равно «дс» (`DK.resolve`). Иначе
    уже выпущенный пакет при повторной выгрузке молча стал бы «Приложением»."""
    return DK.resolve(d.get("kind"), None, is_master=bool(d.get("is_master")))


def _w(d: dict, text: str) -> str:
    """Слово документа в пунктах, вшитых в код, — по виду документа.

    История. С 15.10.2026 ДС мастер-сделки переписывались здесь таблицей замен на
    сокращение: «настоящему Приложению» → «настоящему ДС». 31.10.2026 владелец решил
    («синхронизировать»; «в настройках — ДС, в тексте — Доп. соглашение»): одно слово на
    весь документ, в тексте — полной формой, и решает тумблер договора. Таблица заменена
    общим правилом `DK.rebrand`; мастер-сделка по-прежнему по умолчанию доп. соглашение.
    """
    return DK.rebrand(text, _kind(d))


def _clause_11(d: dict) -> str:
    return _w(d, f"Общая стоимость Услуг Исполнителя по настоящему Приложению составляет сумму "
            f"в размере {d.get('amount_words') or ''}, в том числе НДС "
            f"{d.get('vat_rate')}% — {d.get('vat_words') or ''}. Оплата услуг Исполнителя "
            f"по настоящему Приложению осуществляется Заказчиком на основании "
            f"выставленного счета, счет-фактуры, Акта оказания услуг согласно разделу 4 "
            f"Договора.")


def _clause_3(d: dict) -> str:
    return _w(d, f"Во всем остальном, не урегулированном настоящим Приложением, стороны "
            f"руководствуются положениями Договора. Настоящее Приложение вступает в силу "
            f"с момента его подписания Сторонами и распространяет свое действие на "
            f"отношения Сторон, возникшие с {_dm(d.get('period_from'))} г. Настоящее "
            f"Приложение составлено в 2 (двух) экземплярах, имеющих равную юридическую "
            f"силу, по одному для каждой из Сторон, и является неотъемлемой частью "
            f"Договора.")


def _table(doc, d: dict) -> None:
    """Таблица МП — ячейками `table_cols.view` (колонки шаблона, 17.11.2026) из строк самого документа; колонки и имена
    из справочника кладёт `document.with_table`. Документ без них — прежние 13 колонок тем же расчётом."""
    from app.annex_tpl import table_cols as TC
    tv = TC.view(None, d, d.get("table_columns") or TC.of_blocks(None), d.get("table_names") or {})
    if not tv["rows"]:
        return
    head = tv["head"]
    k = USABLE / sum(c["w"] for c in head)
    widths = [c["w"] * k for c in head]
    t = doc.add_table(rows=1, cols=len(head))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _fixed_layout(t)
    _borders(t)
    for col, w in zip(t.columns, widths):
        col.width = Cm(w)

    for i, (cell, c) in enumerate(zip(t.rows[0].cells, head)):
        _shade(cell, HEADER_FILL)
        cell.width = Cm(widths[i])
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        for j, line in enumerate(c["label"].split("\n")):
            if j:
                p.add_run().add_break()
            _run(p, line, bold=True, size=7, color="FFFFFF")

    for r in tv["rows"]:
        cells = t.add_row().cells
        for i, w in enumerate(widths):
            cells[i].width = Cm(w)
        if r.get("group"):            # заголовок группы ДС мастер-сделки (бренд · услуга) — строкой на всю ширину
            cells[0].merge(cells[len(widths) - 1])
            _cell_text(cells[0], r["group"], bold=True, align="left")
            continue
        for i, (c, v) in enumerate(zip(head, r["cells"])):
            _cell_text(cells[i], v, bold=c["style"] == "bold", italic=c["style"] == "italic", align=c["align"])

    # ИТОГО — по строкам таблицы (считает `view`): колонка и её итог обязаны сходиться на бумаге.
    cells = t.add_row().cells
    for i, w in enumerate(widths):
        cells[i].width = Cm(w)
        _shade(cells[i], TOTAL_FILL)
    span = tv["total"]["span"]
    if span:
        if span > 1:
            cells[0].merge(cells[span - 1])
        _cell_text(cells[0], "ИТОГО:", bold=True, align="right")
    for i in range(span, len(head)):
        if tv["total"]["cells"][i]:
            _cell_text(cells[i], tv["total"]["cells"][i], bold=True, align="right")
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
        for text in (party.get("legal_name") or party.get("name") or "—",
                     party.get("position_nom") or party.get("position") or "____________",
                     "",
                     f"____________________ /{party.get('short_fio') or '_________'}/",
                     "М.П."):
            p = cell.add_paragraph()
            p.alignment = a
            _run(p, text)
