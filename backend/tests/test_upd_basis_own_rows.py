# -*- coding: utf-8 -*-
"""Основание каждой УПД пакета — по строкам СВОЕЙ УПД, а не всего ДС (владелец 03.11.2026).

Поломка, которую ловит: тестовый ДС пакета с 4 УПД (три бренда еФарм WEB + платный «Комплект рекламных материалов» у одного)
печатал у всех четырёх «Размещение рекламных материалов и оказание дополнительных услуг (проведение исследования Sales-Lift,
изготовление комплекта…)»: состав и {услуга} брались по всему ДС, а бонусный Sales-Lift за 0 ₽ шёл в перечень услуг.
"""
from types import SimpleNamespace

from app.annex_tpl import assemble as AS
from app.annex_tpl import document as D

# Три сделки: у 1 и 2 — размещение + бонусный Sales-Lift, у 3 — размещение + платный комплект. Так их кладёт снимок ДС пакета.
ROWS = [
    {"deal_id": 1, "kind": "base", "amount": 576382.09, "position": "еФарм"},
    {"deal_id": 1, "kind": "extra", "amount": None, "bonus": True, "position": "Sales-Lift"},
    {"deal_id": 2, "kind": "base", "amount": 631091.57, "position": "еФарм"},
    {"deal_id": 2, "kind": "extra", "amount": None, "bonus": True, "position": "Sales-Lift"},
    {"deal_id": 3, "kind": "base", "amount": 335233.89, "position": "еФарм"},
    {"deal_id": 3, "kind": "extra", "amount": 20000.0, "bonus": False, "position": "Комплект рекламных материалов"},
]
BRANDS = {1: "Berlin-Chemie / Эспумизан", 2: "Promomed / Райтбуфен", 3: "KRKA / Налгезин"}
PHRASES = {"Sales-Lift": "проведение исследования Sales-Lift",
           "Комплект рекламных материалов": "изготовление комплекта рекламных материалов"}
MODEL = {"values": {"услуга": "проведение исследования Sales-Lift, изготовление комплекта рекламных материалов", "сеть": "SIMB-AD",
                    "вид_документа_дат": "Дополнительному соглашению", "номер_дс": "№1", "дата_дс_кратко": "01.10.26",
                    "договор_номер": "РМ 30-11-2023", "договор_дата_кратко": "30.11.23",
                    "период_с": "01.10.2026", "период_по": "31.10.2026"},
         "closing_basis": {"template": "x", "edited": False, "inherited_from": None}}


def test_kit_rows_by_brand_and_service_skip_zero_bonus():
    """Комплект «бренд · услуга» — только размещение бренда; комплект бренда без услуги — только его платные допы; бонус 0 ₽ — нигде."""
    base = D.upd_rows(ROWS, BRANDS, "KRKA / Налгезин", "еФарм · WEB", by_service=True)
    extra = D.upd_rows(ROWS, BRANDS, "KRKA / Налгезин", None, by_service=True)
    assert [(r["deal_id"], r["kind"]) for r in base] == [(3, "base")]
    assert [(r["deal_id"], r["position"]) for r in extra] == [(3, "Комплект рекламных материалов")]
    assert D.upd_rows(ROWS, BRANDS, "Berlin-Chemie / Эспумизан", None, by_service=True) == []
    # без деления по услугам комплект бренда — всё платное этого бренда
    assert [r["kind"] for r in D.upd_rows(ROWS, BRANDS, "KRKA / Налгезин", None, by_service=False)] == ["base", "extra"]
    # без деления по брендам — все сделки, но бонус по-прежнему не в счёт
    assert len(D.upd_rows(ROWS, BRANDS, None, None, by_service=False)) == 4


def _basis(monkeypatch, brand, service):
    monkeypatch.setattr("app.sales.annex.deal_brand", lambda db, ids: BRANDS[ids[0]])
    monkeypatch.setattr(AS, "_addon_phrases", lambda db: PHRASES)
    monkeypatch.setattr(AS, "_brands_only", lambda db, ids: ", ".join(sorted(BRANDS[i].split(" / ")[-1] for i in ids)))
    db = SimpleNamespace(get=lambda cls, i: SimpleNamespace(upd_by_service=True))
    k = SimpleNamespace(brand=brand, service=service, basis_text=None, master_deal_id=7)
    return D.upd_closing(MODEL, k, ROWS, db=db)["text"]


def test_placement_upd_says_only_placement(monkeypatch):
    assert _basis(monkeypatch, "Berlin-Chemie / Эспумизан", "еФарм · WEB") == (
        "Размещение рекламных материалов бренда «Эспумизан», в сети SIMB-AD, согласно Дополнительному соглашению №1 от 01.10.26 "
        "к Договору РМ 30-11-2023 от 30.11.23г., с 01.10.2026 по 31.10.2026г.")


def test_addon_upd_says_only_its_paid_addon(monkeypatch):
    assert _basis(monkeypatch, "KRKA / Налгезин", None) == (
        "Оказание дополнительных услуг (изготовление комплекта рекламных материалов) для бренда «Налгезин», согласно "
        "Дополнительному соглашению №1 от 01.10.26 к Договору РМ 30-11-2023 от 30.11.23г., с 01.10.2026 по 31.10.2026г.")


def test_edited_template_keeps_text_but_service_is_the_upds_own(monkeypatch):
    """Основание, поправленное в конструкторе, остаётся текстом аккаунта; {услуга} в нём — услуги своей УПД."""
    model = {**MODEL, "closing_basis": {"template": "Услуги: {услуга}.", "edited": True, "inherited_from": None}}
    monkeypatch.setattr("app.sales.annex.deal_brand", lambda db, ids: BRANDS[ids[0]])
    monkeypatch.setattr(AS, "_addon_phrases", lambda db: PHRASES)
    monkeypatch.setattr(AS, "_brands_only", lambda db, ids: "Налгезин")
    db = SimpleNamespace(get=lambda cls, i: SimpleNamespace(upd_by_service=True))
    k = SimpleNamespace(brand="KRKA / Налгезин", service=None, basis_text=None, master_deal_id=7)
    assert D.upd_closing(model, k, ROWS, db=db)["text"] == "Услуги: изготовление комплекта рекламных материалов."


NAMES = {1: "Эспумизан (взрослый) / Espumisan (adults)", 2: "Райтбуфен", 3: "Налгезин"}


def _basis_named(monkeypatch, brand, service, by_service=True):
    monkeypatch.setattr("app.sales.annex.deal_brand", lambda db, ids: BRANDS[ids[0]])
    monkeypatch.setattr(AS, "_addon_phrases", lambda db: PHRASES)
    monkeypatch.setattr(AS, "_brands_only", lambda db, ids: ", ".join(sorted(NAMES[i] for i in ids)))
    db = SimpleNamespace(get=lambda cls, i: SimpleNamespace(upd_by_service=by_service))
    k = SimpleNamespace(brand=brand, service=service, basis_text=None, master_deal_id=7)
    return D.upd_closing(MODEL, k, ROWS, db=db)["text"]


def test_brand_with_slash_in_its_name_is_not_cut(monkeypatch):
    """«Эспумизан (взрослый) / Espumisan (adults)» — имя бренда из справочника; резать по последнему « / » нельзя (было «Espumisan (adults)»)."""
    assert "бренда «Эспумизан (взрослый) / Espumisan (adults)»," in _basis_named(monkeypatch, "Berlin-Chemie / Эспумизан", "еФарм · WEB")


def test_upd_without_brand_split_names_only_its_own_brands(monkeypatch):
    """УПД допов без деления по брендам: комплект только у Налгезина — в основании только он, а не все три бренда ДС."""
    assert _basis_named(monkeypatch, None, None).startswith(
        "Оказание дополнительных услуг (изготовление комплекта рекламных материалов) для бренда «Налгезин»,")
