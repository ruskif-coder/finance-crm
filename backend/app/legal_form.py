# -*- coding: utf-8 -*-
"""Форма организации контрагента (владелец 04.11.2026; колонка `counterparties.legal_form`, миграция
2026-11-05_counterparty_legal_form.sql).

Зачем: ИП с 12-значным ИНН не регистрировался в ОРД — по ИНН ИП не отличить от физлица, а форму хранить было негде.
Одна точка на перечень, догадку по названию (начальное заполнение и форма заведения — то же правило, что в миграции)
и перевод в форму ОРД.
"""
import re
from typing import Optional

FORMS = ("ООО", "АО", "ПАО", "ИП", "самозанятый", "физлицо", "иностранная организация")

# Форма в ОРД (`CreateClientRequest.legalForm`, спека v3).
_ORD = {"ООО": "JuridicalPerson", "АО": "JuridicalPerson", "ПАО": "JuridicalPerson",
        "ИП": "IndividualEntrepreneur", "самозанятый": "PhysicalPerson", "физлицо": "PhysicalPerson",
        "иностранная организация": "InternationalJuridicalPerson"}

# Отдельным словом в начале или в конце названия; ПАО раньше АО — иначе «ПАО» читалось бы как «АО».
_GUESS = [(f, re.compile(rf'^\s*{f}(?:[\s«"]|$)|[\s»"]{f}\s*$')) for f in ("ПАО", "АО", "ООО", "ИП")]


def guess(name: Optional[str]) -> Optional[str]:
    """Форма по названию юрлица — или None, если в названии её нет."""
    for form, rx in _GUESS:
        if rx.search(name or ""):
            return form
    return None


def ord_code(form: Optional[str]) -> Optional[str]:
    """Форма в ОРД; незнакомая или пустая — None (вызывающий решает по длине ИНН)."""
    return _ORD.get(form or "")
