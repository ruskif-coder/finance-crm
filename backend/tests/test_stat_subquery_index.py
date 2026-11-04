# -*- coding: utf-8 -*-
"""Подзапрос факта площадки обязан нести РК — иначе он читает всю статистику на каждую площадку.

Поломка, которую ловит: `(SELECT sum(s.shows) FROM ad_campaign_stat s WHERE s.placement_id = p.id …)`. Индекса по одной
площадке у `ad_campaign_stat` нет (уникальный ключ начинается с `campaign_id`), и Postgres делал полный проход таблицы
на каждую из ~1200 площадок: дашборд аккаунта ждал 2,7 с, из них 2,2 с — два таких подзапроса (замер 03.11.2026).
С `s.campaign_id = p.campaign_id` — проход по индексу `uq_ad_stat`, 13 мс вместо 1360.
"""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
BARE = re.compile(r"WHERE\s+s\.placement_id\s*=\s*p\.id")


def test_placement_fact_subqueries_carry_the_campaign():
    bad = []
    for f in APP.rglob("*.py"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if BARE.search(line):
                bad.append(f"{f.relative_to(APP)}:{i}")
    assert bad == [], "подзапрос статистики по площадке без РК — полный проход таблицы: " + ", ".join(bad)


def test_instrument_catches_the_old_form():
    old = "(SELECT sum(s.shows) FROM ad_campaign_stat s\n WHERE s.placement_id = p.id AND s.source = ANY(:src)) AS fact"
    new = old.replace("WHERE s.placement_id", "WHERE s.campaign_id = p.campaign_id AND s.placement_id")
    assert BARE.search(old) and not BARE.search(new)
