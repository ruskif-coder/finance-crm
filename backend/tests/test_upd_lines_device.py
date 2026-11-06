# -*- coding: utf-8 -*-
"""Строки УПД со своим основанием (владелец 06.11.2026: «вариант 3»; «в сети SIMB-AD (WEB)»).

В одну УПД раскладка кладёт строки одного бренда — в т. ч. WEB и APP услуги с раздельным прайсом (еФарм). Каждая строка ДС — своя
строка УПД, и её основание называет свой девайс, как он заведён в сделке (строка МП → `device` строки ДС). Метка — только у услуг
с раздельным прайсом (то же правило, что метка WEB/APP в имени сделки, 03.09.2026).

Поломка, которую ловит: обе строки УПД с одним текстом без WEB/APP — в 1С не понять, где что."""
from app.annex_tpl import document as D

TPL = "Размещение бренда «{бренд_название}», в сети {сеть}, с {период_с} по {период_по}г."
VALUES = {"бренд_название": "Бренд", "сеть": "SIMB-AD", "период_с": "01.10.2026", "период_по": "31.10.2026"}


def _row(rid, dev, pos="еФарм", f="2026-10-01", t="2026-10-15"):
    return {"row_id": rid, "device": dev, "position": pos, "date_from": f, "date_to": t, "amount": 100.0, "kind": "base"}


def test_web_and_app_rows_get_their_own_basis():
    lines = D.line_bases(TPL, VALUES, [_row(1, "WEB"), _row(2, "APP", t="2026-10-20")], {"еФарм"})
    assert [x["row_id"] for x in lines] == [1, 2]
    assert lines[0]["text"] == "Размещение бренда «Бренд», в сети SIMB-AD (WEB), с 01.10.2026 по 15.10.2026г."
    assert lines[1]["text"] == "Размещение бренда «Бренд», в сети SIMB-AD (APP), с 01.10.2026 по 20.10.2026г."


def test_no_label_for_service_without_separate_price_or_cross_device():
    lines = D.line_bases(TPL, VALUES, [_row(1, "WEB", pos="Альфарм"), _row(2, "Кросс-девайс")], {"еФарм"})
    assert all("SIMB-AD," in x["text"] for x in lines), [x["text"] for x in lines]


def test_kit_of_one_device_gets_label_in_its_single_basis():
    v = D.with_device(VALUES, [_row(1, "WEB"), _row(2, "WEB")], {"еФарм"})
    assert v["сеть"] == "SIMB-AD (WEB)"
    assert D.with_device(VALUES, [_row(1, "WEB"), _row(2, "APP")], {"еФарм"})["сеть"] == "SIMB-AD", "разные девайсы — общий текст без метки"


def _upd_xml(names) -> bytes:
    rows = "".join(f'<СведТов НомСтр="{i}" НаимТов="{n}"/>' for i, n in enumerate(names, 1))
    return (f'<?xml version="1.0" encoding="utf-8"?><Файл><Документ><СвСчФакт НомерДок="1" ДатаДок="31.10.2026">'
            f'<СвПокуп><ИдСв><СвЮЛУч ИННЮЛ="7700000001" КПП="770001001"/></ИдСв></СвПокуп></СвСчФакт>'
            f'<ТаблСчФакт>{rows}<ВсегоОпл СтТовБезНДСВсего="1" СтТовУчНалВсего="1.22"/></ТаблСчФакт></Документ></Файл>').encode()


def test_xml_needs_every_line_basis_of_multiline_upd():
    from app.onec_desk import xmlparse as XP
    web, app_ = "Размещение … в сети SIMB-AD (WEB) …", "Размещение … в сети SIMB-AD (APP) …"
    ours = web + "\n" + app_
    assert XP.parse(_upd_xml([app_, web]), None, ours)["basis"] == ours, "обе строки есть — порядок не важен"
    assert XP.parse(_upd_xml([web]), None, ours)["basis"] != ours, "строки APP в УПД нет — не совпало"


def test_upd_by_service_takes_only_rows_of_its_device():
    """«УПД по услугам»: «еФарм · WEB» и «еФарм · APP» — разные УПД (раскладка, 28.10.2026). Строки УПД, её сумма и основание —
    только своей площадки; раньше в обе УПД M-0001 попадали обе строки."""
    rows = [{"deal_id": 1, "device": "WEB", "amount": 100.0, "kind": "base"},
            {"deal_id": 2, "device": "APP", "amount": 50.0, "kind": "base"},
            {"deal_id": 1, "amount": 10.0, "kind": "extra"}]
    svc = {1: "еФарм", 2: "еФарм"}
    web = D.upd_rows(rows, {}, None, "еФарм · WEB", by_service=True, service_of=svc)
    app_ = D.upd_rows(rows, {}, None, "еФарм · APP", by_service=True, service_of=svc)
    assert [r["device"] for r in web] == ["WEB"] and [r["device"] for r in app_] == ["APP"]
    assert [r["kind"] for r in D.upd_rows(rows, {}, None, None, by_service=True, service_of=svc)] == ["extra"], "УПД допов — только допы"
