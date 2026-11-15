# -*- coding: utf-8 -*-
"""Форма организации контрагента (владелец 04.11.2026; колонка `counterparties.legal_form`, миграция
2026-11-05_counterparty_legal_form.sql).

Зачем: ИП с 12-значным ИНН не регистрировался в ОРД — по ИНН ИП не отличить от физлица, а форму хранить было негде.
Одна точка на перечень и перевод в форму ОРД. Догадка формы по названию живёт только в миграции начального заполнения
(функция-двойник `guess` без вызовов удалена 15.11.2026).
"""
from typing import Optional

FORMS = ("ООО", "АО", "ПАО", "ИП", "самозанятый", "физлицо", "иностранная организация")

# Форма в ОРД (`CreateClientRequest.legalForm`, спека v3).
_ORD = {"ООО": "JuridicalPerson", "АО": "JuridicalPerson", "ПАО": "JuridicalPerson",
        "ИП": "IndividualEntrepreneur", "самозанятый": "PhysicalPerson", "физлицо": "PhysicalPerson",
        "иностранная организация": "InternationalJuridicalPerson"}



def ord_code(form: Optional[str]) -> Optional[str]:
    """Форма в ОРД; незнакомая или пустая — None (вызывающий решает по длине ИНН)."""
    return _ORD.get(form or "")
