# -*- coding: utf-8 -*-
"""XML счёта на оплату для Диадока по формату ФНС (КНД 1110379, схема ON_CHETOP_1_998_01_05_01_04; владелец 12.11.2026:
«формировать xml для диадока на основании нашего счёта, чтобы не заполнять данные вручную»).

Поломки, которые ловит набор:
- файл не проходит схему ФНС (Диадок его не примет как формализованный счёт);
- сумма в XML расходится со счётом 1С (номер и дата — из 1С, суммы — наши строки: расхождение = второй источник);
- в файле не та кодировка или не тот префикс имени;
- счёт без номера/даты из 1С или без подписанта собирается молча."""
import os
from datetime import datetime

import pytest
from lxml import etree

from app.onec_desk import invoice_xml as IX

XSD = os.path.join(os.path.dirname(IX.__file__), "xsd", "ON_CHETOP_1_998_01_05_01_04.xsd")


def _inv(**kw):
    inv = {
        "number": "288", "date": "2026-11-06",
        "seller": {"name": "ООО «Продавец»", "inn": "7700000001", "kpp": "770001001", "address": "г. Москва, ул. Тестовая, 1",
                   "edo_id": None, "bank": {"account": "40702810000000000001", "bik": "044599001", "corr": "30101810000000000901",
                                            "name": "ТЕСТ-БАНК"},
                   "signer": {"position": "Генеральный директор", "fio": "Тестов Тест Тестович"}},
        "buyer": {"name": "ООО «Покупатель»", "inn": "7700000002", "kpp": "770002001", "address": "г. Москва, ул. Пробная, 2",
                  "edo_id": None},
        "basis": {"name": "Договор", "number": "РМ-21-11-25", "date": "2025-11-21"},
        "purpose": "Оплата по счёту № 288 от 06.11.2026",
        "lines": [{"name": "Размещение рекламных материалов", "net": 361333.43, "vat_rate": 22, "vat": 79493.35, "gross": 440826.78},
                  {"name": "Изготовление комплекта", "net": 20000.00, "vat_rate": 22, "vat": 4400.00, "gross": 24400.00}],
    }
    inv.update(kw)
    return inv


NOW = datetime(2026, 11, 12, 19, 30, 5)


def test_xml_passes_the_fns_schema_and_is_windows_1251():
    name, data = IX.build(_inv(), NOW)
    assert data.startswith(b'<?xml version="1.0" encoding="windows-1251"?>')
    doc = etree.fromstring(data)
    schema = etree.XMLSchema(etree.parse(XSD))
    assert schema.validate(doc), schema.error_log
    assert name.startswith("ON_CHETOP_7700000002_770002001_7700000001_770001001_20261112_") and name.endswith(".xml")
    assert doc.get("ИдФайл") == name[:-4]


def test_totals_are_the_sum_of_lines_counted_by_hand():
    _, data = IX.build(_inv(), NOW)
    doc = etree.fromstring(data)
    total = doc.find(".//ВсегоОпл")
    assert (total.get("СтТовБезНДСВсего"), total.get("СтТовУчНалВсего"), total.find("СумНалВсего/СумНал").text) == \
        ("381333.43", "465226.78", "83893.35")
    sc = doc.find(".//СодСч")
    assert (sc.get("НомерДок"), sc.get("ДатаДок")) == ("288", "06.11.2026")
    assert [x.find("НалСт").text for x in doc.findall(".//СведТовЦенПок")] == ["22%", "22%"]


def test_edo_ids_go_to_the_file_name_when_known():
    inv = _inv()
    inv["seller"]["edo_id"], inv["buyer"]["edo_id"] = "2BM-7700000001-2012", "2BM-7700000002-2012"
    name, _ = IX.build(inv, NOW)
    assert name.startswith("ON_CHETOP_2BM-7700000002-2012_2BM-7700000001-2012_20261112_")


@pytest.mark.parametrize("patch, word", [
    ({"number": ""}, "номер"),
    ({"date": None}, "дат"),
])
def test_refuses_without_1c_number_or_date(patch, word):
    with pytest.raises(IX.InvoiceXmlError) as e:
        IX.build(_inv(**patch), NOW)
    assert word in e.value.message


def test_refuses_without_signer():
    inv = _inv()
    inv["seller"]["signer"] = {"position": "", "fio": ""}
    with pytest.raises(IX.InvoiceXmlError) as e:
        IX.build(inv, NOW)
    assert "подписант" in e.value.message


# ── ревью 12.11.2026: страховки — на данных случаев ноль, но файл должен быть годным или отказ внятным ──────────

def _valid(data):
    return etree.XMLSchema(etree.parse(XSD)).validate(etree.fromstring(data))


def test_sole_trader_buyer_goes_as_svip_and_passes_schema():
    inv = _inv()
    inv["buyer"] = {"name": "ИП Петров Пётр Петрович", "inn": "770000000003", "kpp": None, "address": None, "edo_id": None}
    _, data = IX.build(inv, NOW)
    doc = etree.fromstring(data)
    assert doc.find(".//СвПокуп/ИдСв/СвИП").get("ИННФЛ") == "770000000003" and _valid(data)


def test_lines_without_vat_say_bez_nds_in_lines_and_total():
    inv = _inv(lines=[{"name": "Услуга", "net": 1000, "vat_rate": 0, "vat": 0, "gross": 1000}])
    _, data = IX.build(inv, NOW)
    doc = etree.fromstring(data)
    assert doc.find(".//СведТовЦенПок/НалСт").text == "без НДС"
    assert doc.find(".//ВсегоОпл/СумНалВсего/БезНДС").text == "без НДС" and _valid(data)


def test_no_seller_bank_is_refused_not_an_invalid_file():
    inv = _inv()
    inv["seller"]["bank"] = None
    with pytest.raises(IX.InvoiceXmlError) as e:
        IX.build(inv, NOW)
    assert "банк" in e.value.message


def test_total_is_the_sum_of_printed_lines():
    inv = _inv(lines=[{"name": "a", "net": 0.005, "vat_rate": 22, "vat": 0.001, "gross": 0.006}] * 3)
    _, data = IX.build(inv, NOW)
    t = etree.fromstring(data).find(".//ВсегоОпл")
    assert t.get("СтТовБезНДСВсего") == "0.03" and t.get("СтТовУчНалВсего") == "0.03"


def test_characters_outside_cp1251_are_kept_not_replaced_with_question_marks():
    inv = _inv()
    inv["buyer"]["name"] = "ООО «Café ₽»"
    _, data = IX.build(inv, NOW)
    assert etree.fromstring(data).find(".//СвПокуп/ИдСв/СвЮЛУч").get("НаимОрг") == "ООО «Café ₽»"
