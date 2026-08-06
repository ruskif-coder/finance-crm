"""Единая защита от formula/CSV-injection в Excel-выгрузках.

openpyxl пишет строку, начинающуюся с = + - @, как живую формулу/DDE — при открытии
файла получателем (часто внешним клиентом) это исполняется. Экранируем ведущей кавычкой.
Используется во всех экспортах (.xlsx): media_plans, operations, contracts."""


def xlsx_safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v
