# -*- coding: utf-8 -*-
"""Название юрлица в документе: аббревиатурой, как в образце шаблона — «ООО «Ромашка»», «ИП Иванов Иван Иванович» (владелец 14.10.2026).

В реестре контрагентов форма стоит в конце («ГРИНДЕКС РУС ООО», «Лукин Евгений Витальевич ИП») — наследие выгрузки; в документе она идёт
впереди, название организации — в кавычках. Незнакомое или уже оформленное название возвращается как есть: тихая правка чужого имени хуже
неправильного порядка слов — её не видно, а ошибку в реквизитах подписывают.
"""
import re
from typing import Optional

COMPANY_FORMS = ("ООО", "АО", "ПАО", "ЗАО", "ОАО", "НКО", "АНО", "ГУП", "МУП", "ФГУП")
PERSON_FORMS = ("ИП",)
LONG_IP = "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ"
_QUOTES = '«»"“”„'


def _strip_quotes(s: str) -> str:
    return s.strip().strip(_QUOTES).strip()


def legal_name(name: Optional[str]) -> str:
    n = " ".join((name or "").split())
    if not n:
        return ""
    # «… ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ» → «ИП …»
    if n.upper().endswith(LONG_IP):
        rest = n[: -len(LONG_IP)].strip()
        return f"ИП {rest}" if rest else n
    head, _, tail = n.partition(" ")
    last = n.rsplit(" ", 1)[-1] if " " in n else ""
    # уже оформлено: «ООО «Ромашка»», «ИП Иванов»
    if head.upper() in COMPANY_FORMS and "«" in tail:
        return n
    if head.upper() in PERSON_FORMS:
        return n
    # форма в конце: «ГРИНДЕКС РУС ООО» / «Лукин Евгений ИП»
    if last.upper() in COMPANY_FORMS and len(n) > len(last) + 1:
        return f"{last.upper()} «{_strip_quotes(n[: -len(last)])}»"
    if last.upper() in PERSON_FORMS and len(n) > len(last) + 1:
        return f"ИП {n[: -len(last)].strip()}"
    # форма впереди без кавычек: «ООО Ромашка»
    if head.upper() in COMPANY_FORMS and tail:
        return f"{head.upper()} «{_strip_quotes(tail)}»"
    return n


def has_form(name: Optional[str]) -> bool:
    return bool(re.match(r"^(ООО|АО|ПАО|ЗАО|ОАО|НКО|АНО|ГУП|МУП|ФГУП|ИП)\b", legal_name(name)))
