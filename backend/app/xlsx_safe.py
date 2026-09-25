"""Единая защита от formula/CSV-injection в Excel-выгрузках.

openpyxl пишет строку, начинающуюся с = + - @, как живую формулу/DDE — при открытии
файла получателем (часто внешним клиентом) это исполняется. Экранируем ведущей кавычкой.
Используется во всех экспортах (.xlsx): media_plans, operations, contracts.

С 24.09.2026 (аудит 23.09.2026, 1.L7) главная линия — `save_workbook`: `xlsx_safe`
применяли 3 выгрузки из 9, а у остальных текст пользователя уходил в файл формулой.
Оборачивать каждую запись ячейки ненадёжно — следующий новый столбец снова забудут.
Поэтому книга сохраняется ТОЛЬКО через `save_workbook` (гейт
`tests/test_xlsx_formula_guard.py`), и перед сохранением каждая формула сверяется с
грамматикой формул, которые ставит сам код: адреса ячеек и диапазоны, числа,
арифметика, короткие строковые литералы и функции из `SAFE_FUNCTIONS`. Всё, что в неё
не укладывается — HYPERLINK, WEBSERVICE, DDE `cmd|…`, ссылки на другие книги и листы, —
пишется ТЕКСТОМ. Текст пользователя вида «=1+1» остаётся формулой: он вычисляется, но
ничего не вызывает наружу — это не инъекция.
"""
import re

# Функции, которые ставит в ячейки сам код (media_plans, year_mp_export, finreport).
# Новая функция в формуле кода — добавить её сюда осознанно; иначе она уедет текстом.
SAFE_FUNCTIONS = ("SUM", "IF", "AND", "OR", "CONCATENATE", "TEXT", "ROUND", "IFERROR",
                  "MAX", "MIN", "ABS")

# Ссылка на лист: 'Имя листа'!A1 или Имя!A1. Имя сверяется со списком листов ЭТОЙ книги:
# ссылка на другую книгу (`[1]Лист!A1`) или DDE (`cmd|' /C calc'!A0`) сюда не проходит.
_SHEET = re.compile(r"(?:'([^'\[\]|!]{1,31})'|([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё.]{0,30}))!")

_TOKEN = re.compile(
    r"\s+"
    r"|\$?[A-Z]{1,3}\$?\d{1,7}(?::\$?[A-Z]{1,3}\$?\d{1,7})?(?![A-Za-z0-9_(!])"
    r"|\d+(?:\.\d+)?%?"
    r"|(?:" + "|".join(SAFE_FUNCTIONS) + r")\("
    r"|\"[^\"\n]{0,40}\""
    r"|<>|<=|>=|[-+*/^&=<>(),:]",
    re.ASCII,     # \d — только 0-9: цифры других письменностей дают битый файл (ревью 24.09.2026)
)


def xlsx_safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def formula_is_ours(text: str, sheets=()) -> bool:
    """Формула целиком состоит из разрешённых лексем — значит, её мог поставить код.
    `sheets` — листы этой книги: ссылаться можно только на них."""
    if not isinstance(text, str) or not text.startswith("="):
        return False
    body, pos = text[1:], 0
    while pos < len(body):
        sm = _SHEET.match(body, pos)
        if sm:
            if (sm.group(1) or sm.group(2)) not in sheets:
                return False
            pos = sm.end()
            continue
        m = _TOKEN.match(body, pos)
        if not m or m.end() == pos:
            return False
        pos = m.end()
    return True


def neutralize_workbook(wb) -> int:
    """Все формулы не из грамматики кода → текст. Возвращает, сколько обезврежено."""
    n = 0
    sheets = set(wb.sheetnames)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.startswith("=") and not formula_is_ours(v, sheets):
                    cell.data_type = "s"       # то же значение, но строкой — Excel не исполнит
                    n += 1
    return n


def save_workbook(wb, target) -> None:
    """Единственная точка сохранения выгрузок .xlsx."""
    neutralize_workbook(wb)
    wb.save(target)
