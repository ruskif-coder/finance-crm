# -*- coding: utf-8 -*-
"""Сопоставление строк Excel продаж со справочником (22.10.2026) — на написаниях из реального листа, справочник подменён."""
import pytest

from app.sales.status_match import Directory, latin, parts

ADV = [(1, ["BIOCAD", "Биокад", None]), (2, ["Валента Фарм", "Валента"]), (3, ["Акрихин"]), (4, ["Roche", "Рош"]),
       (5, ["Bionorica", "Бионорика"]), (6, ["Novartis"]), (7, ["Abbott"]), (8, ["ЛЕОВИТ"]), (9, ["Materia Medica"]), (20, ["AstraZeneca"])]
BR = [(10, 2, "Ингавирин"), (11, 2, "Граммидин"), (12, 3, "Аквадетрим"), (13, 3, "Акридерм"), (14, 4, "Антелиос"),
      (15, 5, "Тонзилгон"), (16, 7, "Финитабс"), (17, 7, "Креон"), (18, 8, "Леовит Окно")]
D = Directory(ADV, BR)


def test_latin_unifies_scripts():
    assert latin("Биокад") == latin("BIOCAD")
    assert latin("Новартис") == latin("Novartis")


def test_parts_split_brackets_and_lists():
    assert {"валента", "ингавирин", "граммидин"} <= set(parts("Валента (Ингавирин, Граммидин)"))


@pytest.mark.parametrize("client,adv,brands", [
    ("BIOCAD (БИОКАД)", 1, []),
    ("Биокад", 1, []),
    ("Валента (Ингавирин, Граммидин, Антарейд)", 2, [10, 11]),
    ("Акрихин аквадетрим", 3, [12]),
    ("ANTELIOS (Антелиос) - Roche", 4, [14]),
    ("Бионорика (тонзиглон)", 5, [15]),          # опечатка в бренде: тонзиглон / тонзилгон
    ("Novartiss", 6, []),                        # опечатка в рекламодателе
    ("Abbott (финитабс)", 7, [16]),
])
def test_match(client, adv, brands):
    m = D.match(client)
    assert m is not None and m.advertiser_id == adv and sorted(m.brand_ids) == brands


def test_brand_without_advertiser_finds_its_owner():
    m = D.match("Креон 2026")
    assert m and m.advertiser_id == 7 and m.brand_ids == [17]


@pytest.mark.parametrize("client", ["Huawei", "Lamoda", "АБИ продукт"])
def test_unknown_stays_unmatched(client):
    assert D.match(client) is None


def test_fuzzy_does_not_join_multiword_names():
    """«леовит (онко)» — не «Леовит Окно»: у онко/окно почти те же буквы, но это другой бренд (сверка 22.10.2026)."""
    m = D.match("леовит (онко)")
    assert m and m.advertiser_id == 8 and m.brand_ids == []


@pytest.mark.parametrize("client,adv", [("материамедика (Импаза)", 9), ("Нексиум - Астра Зенека", 20)])
def test_spacing_does_not_matter_for_advertisers(client, adv):
    """«материамедика» = «Materia Medica», «Астра Зенека» = «AstraZeneca»: слитное написание сравнивается целиком."""
    m = D.match(client)
    assert m and m.advertiser_id == adv
