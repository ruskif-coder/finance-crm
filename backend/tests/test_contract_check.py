# -*- coding: utf-8 -*-
"""Данные договора для ликвидного ДС (владелец 21.10.2026): номер, дата, контрагент, канал, наше юрлицо; ИНН по контрольной
сумме, КПП у юрлица. Строки ложатся в `missing` модели — то есть запирают подтверждение и выгрузку."""
from datetime import date
from types import SimpleNamespace as NS

from app.annex_tpl import contract_check as CC


def test_inn_checksum():
    assert CC.inn_ok("7707083893")            # Сбербанк — юрлицо
    assert CC.inn_ok("500100732259")          # ИП, 12 цифр
    assert not CC.inn_ok("7707083894")
    assert not CC.inn_ok("12345")
    assert not CC.inn_ok("")


def _contract(**kw):
    base = dict(contract_number="РМ-1", contract_date=date(2024, 1, 1), counterparty_id=1, issue_channel="ЭДО",
                counterparty=NS(inn="7707083893", kpp="773601001"), own_company=NS(inn="7707083893", kpp="770701001"))
    return NS(**{**base, **kw})


def test_complete_contract_has_no_gaps():
    assert CC.gaps(None, _contract()) == []


def test_each_gap_is_named_with_where_to_fix():
    c = _contract(contract_number="", contract_date=None, counterparty_id=None, issue_channel=None,
                  counterparty=NS(inn="7707083894", kpp="773601001"), own_company=NS(inn="7707083893", kpp=""))
    texts = [g["text"] for g in CC.gaps(None, c)]
    assert texts == ["договор: номер", "договор: дата", "договор не привязан к контрагенту из реестра",
                     "договор: выставление — ЭДО или бумага",
                     "заказчик: ИНН 7707083894 не проходит проверку контрольной суммы", "исполнитель: КПП (у юрлица обязателен)"]
    assert all(g["where"] for g in CC.gaps(None, c))


def test_entrepreneur_needs_no_kpp():
    assert CC.gaps(None, _contract(counterparty=NS(inn="500100732259", kpp=None))) == []
