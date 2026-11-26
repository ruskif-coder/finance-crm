# -*- coding: utf-8 -*-
"""`{единицы_сделки}` — единицы закупки и объёмы строк (владелец 26.11.2026).

Владелец: «нужна новая переменная — единицы сделки — по ним подставляем объёмы закупки». Форма — «показы —
1 361 948», несколько единиц через «; »; в основании УПД — объём СВОЕЙ УПД; у доп. услуги штуки = сумма ÷ цена;
бонус в фразу не попадает и печать не запирает.

Поломки, которые держат эти приборы:
1. фраза печатает число не тем форматом, что колонка «Объём» таблицы (текст и таблица расходятся);
2. слово единицы считается не тем правилом, что колонка «Единица измерения» (CPC напечатан показами);
3. основание УПД берёт объём ВСЕГО ДС, а не своих строк (в мультибрендовом ДС чужой объём);
4. пустая фраза запирает выгрузку ДС (владелец: не блокирует).
"""
from types import SimpleNamespace

from app.annex_tpl import assemble as AS
from app.annex_tpl import doc_units as DU
from app.annex_tpl import document as TD
from app.annex_tpl import subs as S
from app.annex_tpl import table_cols as TC


def row(**kw):
    r = {"model": "CPM", "volume": 1000, "kind": "base", "position": "еФарм", "unit_price": 350.0, "amount": 350000.0}
    r.update(kw)
    return r


def test_sample_in_the_tag_list_is_what_the_code_prints():
    """Образец тега в справочнике — не выдуманный: фраза ровно такого вида и получается."""
    assert DU.phrase([row(volume=1361948)]) == S.SUBS["единицы_сделки"]["sample"]


def test_volume_number_is_the_same_format_as_the_table_column():
    r = row(volume=1361948)
    cell = TC.cell(r, {"key": "volume"}, {})
    assert DU.phrase([r]) == f"показы — {cell}"
    assert cell == "1 361 948"


def test_unit_word_is_the_same_rule_as_the_table_unit_column():
    """CPC — клики, Фикс — штуки: то же слово, что в колонке «Единица измерения» (в именительном падеже)."""
    for model, word in (("CPM", "показы"), ("CPC", "клики"), ("Фикс", "штуки"), ("Пакет", "штуки")):
        r = row(model=model, volume=120, unit_price=10.0, amount=1200.0)
        assert TC.unit_of(r) == word
        assert DU.phrase([r]).split(" — ")[0] == word


def test_two_units_go_in_one_phrase_in_a_stable_order():
    """Размещение и доп. услуга в одном ДС: «показы …; штуки 1» — порядок постоянный, а не по строкам документа."""
    rows = [row(kind="extra", model="Полная цена", volume=None, unit_price=30000.0, amount=30000.0),
            row(volume=1361948)]
    assert DU.phrase(rows) == "показы — 1 361 948; штуки — 1"
    assert DU.phrase(list(reversed(rows))) == DU.phrase(rows)


def test_addon_without_volume_counts_pieces_by_money():
    """У доп. услуги в старых снимках ДС объёма нет: штуки = сумма ÷ цена, а не ноль и не пустая строка."""
    r = row(kind="extra", model="Фикс, ₽", volume=None, unit_price=20000.0, amount=60000.0)
    assert DU.phrase([r]) == "штуки — 3"


def test_addon_by_results_counts_showings():
    r = row(kind="extra", model="Фикс, ₽", volume=250000, period="по итогам РК")
    assert DU.phrase([r]) == "показы — 250 000"


def test_bonus_and_discount_do_not_enter_the_phrase():
    rows = [row(kind="extra", model="Бонус", volume=None, unit_price=150000.0, amount=0.0, bonus=True),
            row(kind="discount", volume=None, amount=-1000.0),
            row(volume=1000)]
    assert DU.phrase(rows) == "показы — 1 000"


def test_empty_phrase_does_not_block_the_document():
    """Одни бонусы — объёма нет: фраза пустая, и печать из-за неё не запирается (владелец 26.11.2026)."""
    bonus = [row(kind="extra", model="Бонус", volume=None, unit_price=150000.0, amount=0.0, bonus=True)]
    assert DU.phrase(bonus) == ""
    assert S.SUBS["единицы_сделки"]["optional"] is True
    missing = AS._missing({"единицы_сделки": True}, {"missing": []}, {"missing": []}, [row()], "Бренд")
    assert not [m for m in missing if "единицы" in m["text"]]
    # и наоборот: незаполненный обязательный тег по-прежнему называет, где заполнить
    other = AS._missing({"рекламодатель": True}, {"missing": []}, {"missing": []}, [row()], "Бренд")
    assert [m for m in other if "рекламодатель" in m["text"]]


def test_values_carry_the_phrase_into_the_document():
    contract = SimpleNamespace(contract_number="РМ 1", contract_date=None)
    v = AS._values(no=1, contract=contract, period_from=None, period_to=None, rate=22.0,
                   gross=1000.0, vat=180.0, brand="Бренд", advertisers="Рекла", units_text="показы — 1 000")
    assert v["единицы_сделки"] == "показы — 1 000"


def test_upd_basis_takes_the_volume_of_its_own_lines():
    """Основание УПД: текст — по её строкам, построчные основания — по своей строке каждый."""
    model = {"values": {"сеть": "SIMB-AD", "период_с": "01.10.2026", "период_по": "31.10.2026"}, "closing_basis": {}}
    k = SimpleNamespace(brand=None, basis_text="Объём: {единицы_сделки}", master_deal_id=None)
    rows = [row(volume=700, date_from="2026-10-01", date_to="2026-10-31", row_id=1),
            row(volume=300, date_from="2026-10-05", date_to="2026-10-31", row_id=2)]
    out = TD.upd_closing(model, k, rows, db=None)
    assert out["text"] == "Объём: показы — 1 000"
    assert [x["text"] for x in out["lines"]] == ["Объём: показы — 700", "Объём: показы — 300"]
