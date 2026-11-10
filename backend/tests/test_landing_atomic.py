# -*- coding: utf-8 -*-
"""Посадочная — ОДНА ссылка (владелец 09.11.2026: «ссылка должна быть атомарна», «не давать» — ни аккаунту, ни площадке).
Было: в RLXATY/BWSDLX у экономаптеки три товара через «;», у фармии два через пробелы — вместо ссылки на подборку. Ломается,
если правило снова пропустит склейку или начнёт резать законную запятую внутри адреса (`?id=11680,11681`, фильтры поиска)."""
import pytest

from app.launch_prep import pub_rules as R

GLUED = [
    "https://economapteka.ru/catalog/product/spazmalgon-tab-20/; https://economapteka.ru/catalog/product/spazmalgon-tab-50-1/",
    "https://economapteka.ru/a/;https://economapteka.ru/b/",
    "https://farmiya.ru/spazmalgon-20-13534  https://farmiya.ru/spazmalgon-50-234910",
    "https://a.ru/x,https://a.ru/y",
    "https://a.ru/x | www.a.ru/y",
    "https://a.ru/x\nhttps://a.ru/y",
]
ATOMIC = [
    "https://120на80.рф/products/special-offer/1?id=11680,11681",
    "https://newapteka.ru/search/%D0%B8/2/0/5/0/1/1/0/0/0/0/0/0/0/0/29,18230/0",
    "https://zdesapteka.ru/catalog/?q=x&filter=price%3A363,608,,%3Bcategories%3A1166",
    "https://track.example/r?url=https://shop.example/p",
]


@pytest.mark.parametrize("v", GLUED)
def test_glued_links_are_refused_for_web_landing(v):
    with pytest.raises(ValueError, match="одна ссылка"):
        R.validate_landing(v)


@pytest.mark.parametrize("v", GLUED)
def test_glued_links_are_refused_for_app_link(v):
    with pytest.raises(ValueError):
        R.validate_app_link(v)


@pytest.mark.parametrize("v", ATOMIC)
def test_comma_inside_one_address_is_fine(v):
    assert R.validate_landing(v) == v


def test_message_tells_what_to_do_instead():
    with pytest.raises(ValueError) as e:
        R.validate_landing(GLUED[0])
    assert "подборк" in str(e.value)
