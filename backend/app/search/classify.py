"""Что за строку ввели в поиск — до запроса к базе.

Одна функция на всю систему: её же потом возьмут бот в Телеграме (сегодня он понимает
только `/start` и код привязки) и глубокие ссылки уведомлений. Три распознавателя одной
и той же строки разошлись бы.

Шаблон сужает типы: код сделки ищется только среди сделок, ИНН — у контрагентов и
договоров. `types = None` — обычный текст, ищем по всем разрешённым типам.
"""
import re

# Код сделки — наш 6-значный отпечаток (`SalesDeal.code`). Только заглавные: слово
# латиницей из шести строчных («berlin») — текст, а не код. Сделки с таким кодом может
# не оказаться — тогда движок откатывается к тексту (engine.run), см. там.
DEAL_CODE = re.compile(r"^[0-9A-Z]{6}$")
INN = re.compile(r"^(\d{10}|\d{12})$")
DIGITS = re.compile(r"^\d+$")
# ЕРИД — токен маркировки в алфавите base58 (без 0, O, I, l). Смешанный регистр И цифра
# обязательны: без этого под шаблон попало бы любое латинское слово с заглавной буквы.
ERID = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{8,64}$")


def _is_erid(q: str) -> bool:
    return (bool(ERID.match(q)) and any(c.isdigit() for c in q)
            and any(c.islower() for c in q) and any(c.isupper() for c in q))


def classify(q: str) -> dict:
    q = (q or "").strip()
    if DEAL_CODE.match(q):
        return {"kind": "deal_code", "types": ["deal"]}
    if INN.match(q):
        return {"kind": "inn", "types": ["counterparty", "contract", "ord_contract"]}
    if DIGITS.match(q):
        # номер Битрикса у сделки, номер договора
        return {"kind": "digits", "types": ["deal", "contract"]}
    if _is_erid(q):
        return {"kind": "erid", "types": ["erid"]}
    return {"kind": "text", "types": None}
