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


# ── 13.11.2026: счёт = документ 1С. Владелец: «пдф — наш счёт, xml который ты генерируешь — они должны совпадать; массовые
# жалобы, что не те счета, описания и формат». Наименования услуг, стороны, адреса и договор — из XML УПД 1С, не из карточек.

UPD = """<?xml version="1.0" encoding="windows-1251"?>
<Файл ИдФайл="x" ВерсФорм="5.03"><Документ><СвСчФакт НомерДок="241" ДатаДок="31.10.2026">
<СвПрод><ИдСв><СвЮЛУч НаимОрг="Общество с ограниченной ответственностью &quot;ПРОДАВЕЦ&quot;" ИННЮЛ="7700000001" КПП="770001001"/></ИдСв>
<Адрес><АдрГАР ИдНом="1b50486f-3854-489f-bb7a-1df3d9cdfc1c" Индекс="105000"><Регион>77</Регион><НаимРегион>Город Москва</НаимРегион>
<МуниципРайон ВидКод="3" Наим="муниципальный округ Тестовый"/><ЭлУлДорСети Тип="пер." Наим="Тестовый"/><Здание Тип="д." Номер="1"/>
<ПомещЗдания Тип="стр." Номер="2"/><ПомещКвартиры Тип="помещ." Номер="3"/></АдрГАР></Адрес>
<БанкРекв НомерСчета="40702810000000000001"><СвБанк НаимБанк="ТЕСТ-БАНК" БИК="044599001" КорСчет="30101810000000000901"/></БанкРекв></СвПрод>
<СвПокуп><ИдСв><СвЮЛУч НаимОрг="ООО &quot;ПОКУПАТЕЛЬ&quot;" ИННЮЛ="7700000002" КПП="770002001"/></ИдСв>
<Адрес><АдрИнф КодСтр="643" НаимСтран="Россия" АдрТекст="125000, Город Москва, ул Пробная, дом 2"/></Адрес></СвПокуп>
<ДокПодтвОтгрНом РеквНаимДок="УПД" РеквНомерДок="241" РеквДатаДок="31.10.2026"/>
</СвСчФакт>
<ТаблСчФакт><СведТов НомСтр="1" НаимТов="Размещение рекламных материалов бренда «Тест», в сети SIMB-AD (WEB), согласно Приложению №3 от 01.10.26 к Договору РМ-05-05-26 от 05.05.26г., с 01.10.2026 по 31.10.2026г." СтТовБезНДС="1000000.36" НалСт="22%" СтТовУчНал="1220000.44"><Акциз><БезАкциз>без акциза</БезАкциз></Акциз><СумНал><СумНал>220000.08</СумНал></СумНал></СведТов>
<ВсегоОпл СтТовБезНДСВсего="1000000.36" СтТовУчНалВсего="1220000.44"><СумНалВсего><СумНал>220000.08</СумНал></СумНалВсего></ВсегоОпл></ТаблСчФакт>
<СвПродПер><СвПер><ОснПер РеквНаимДок="Договор РМ-05-05-26 от 05.05.26г." РеквНомерДок="Договор РМ-05-05-26" РеквДатаДок="05.05.2026"/></СвПер></СвПродПер>
</Документ></Файл>""".encode("cp1251")


def test_invoice_from_1c_upd_matches_1c_texts_and_passes_schema():
    from app.onec_desk import xmlparse as XP
    inv = IX.from_upd(XP.upd_document(UPD), number="316", date="2026-11-11",
                      signer={"position": "Генеральный директор", "fio": "Тестов Тест Тестович"})
    name, data = IX.build(inv, NOW)
    doc = etree.fromstring(data)
    assert _valid(data), etree.XMLSchema(etree.parse(XSD)).error_log
    line = doc.find(".//СведТовЦенПок")
    assert line.get("НаимТов").startswith("Размещение рекламных материалов бренда «Тест»")
    assert (line.get("СтТовБезНДС"), line.get("СтТовУчНал")) == ("1000000.36", "1220000.44")
    assert doc.find(".//СвПрод/ИдСв/СвЮЛУч").get("НаимОрг") == 'Общество с ограниченной ответственностью "ПРОДАВЕЦ"'
    assert doc.find(".//СвПокуп/ИдСв/СвЮЛУч").get("НаимОрг") == 'ООО "ПОКУПАТЕЛЬ"'
    assert doc.find(".//СвПокуп/Адрес/АдрИнф").get("АдрТекст") == "125000, Город Москва, ул Пробная, дом 2"
    assert doc.find(".//СвПрод/Адрес/АдрГАР").get("Индекс") == "105000"          # структурный адрес 1С — как есть
    b = doc.find(".//Основание/ОснРеквДок")
    assert (b.get("РеквНаимДок"), b.get("РеквНомерДок"), b.get("РеквДатаДок")) == ("Договор", "РМ-05-05-26", "05.05.2026")
    assert doc.find(".//СвПрод/БанкРекв").get("НомерСчета") == "40702810000000000001"


def test_no_upd_xml_means_no_invoice_xml():
    with pytest.raises(IX.InvoiceXmlError) as e:
        IX.from_upd(None, number="316", date="2026-11-11", signer={"position": "Директор", "fio": "А Б"})
    assert "XML УПД" in e.value.message


@pytest.mark.parametrize("name, number, want", [
    ("Договор РМ-05-05-26 от 05.05.26г.", "Договор РМ-05-05-26", "РМ-05-05-26"),
    ("Договор", "№ 12", "12"),
    ("Приложение № 3 к договору № 12", "3", None),
])
def test_contract_basis_is_the_contract_not_its_annex(name, number, want):
    from app.onec_desk import xmlparse as XP
    raw = UPD.decode("cp1251").replace('РеквНаимДок="Договор РМ-05-05-26 от 05.05.26г." РеквНомерДок="Договор РМ-05-05-26"',
                                       f'РеквНаимДок="{name}" РеквНомерДок="{number}"').encode("cp1251")
    b = XP.upd_document(raw)["basis"]
    assert (b["number"] if b else None) == want
