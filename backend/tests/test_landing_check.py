# -*- coding: utf-8 -*-
"""Посадочная на домене другой площадки сделки — предупреждение (владелец 16.11.2026: «уведомление, а не запирание»).

Случаи — сегодняшние находки: QGNY4M (посадочные соседних аптек), RLXATY (dagfarm.ru → 120на80.рф, одна сеть ИРИС),
VX2QWE (aptekalegko.ru → newapteka.ru). Уронит: сверка не нормализует кириллический домен / ругается на свой поддомен /
не ругается на чужой домен / подписывает «та же сеть» площадкам разных сетей."""
from app.launch_prep.landing_check import foreign

DEAL = [("farmiya.ru", None), ("farmakopeika.ru", "ИРИС"), ("120на80.рф", "ИРИС"), ("dagfarm.ru", "ИРИС"),
        ("aptekalegko.ru", None), ("newapteka.ru", "ХФ"), ("kuper.ru", None), ("009.рф", None)]


def test_own_domain_and_subdomain_are_fine():
    assert foreign("https://farmiya.ru/polisorb-109787", "farmiya.ru", DEAL) is None
    assert foreign("https://www.farmiya.ru/x", "farmiya.ru", DEAL) is None
    assert foreign("https://web.kuper.ru/multisearch_promo?slug=x", "kuper.ru", DEAL) is None
    assert foreign("https://009.xn--p1ai/search/x", "009.рф", DEAL) is None, "кириллица и punycode — один домен"


def test_neighbour_domain_is_flagged():
    got = foreign("https://farmakopeika.ru/catalog/2440/1276018", "farmiya.ru", DEAL)
    assert got == "посадочная на домене другой площадки сделки: farmakopeika.ru"
    assert foreign("https://newapteka.ru/search//2//5//1/0////1307", "aptekalegko.ru", DEAL, None) \
        == "посадочная на домене другой площадки сделки: newapteka.ru"


def test_same_network_is_flagged_with_a_note():
    got = foreign("https://120на80.рф/catalog/search?q=Спазмалгон", "dagfarm.ru", DEAL, "ИРИС")
    assert got.startswith("посадочная на домене другой площадки сделки: 120на80.рф — та же сеть «ИРИС»")


def test_punycode_link_to_cyrillic_neighbour_is_flagged():
    """Ссылка, скопированная из адресной строки, бывает в punycode — без нормализации чужой домен прошёл бы молча."""
    assert foreign("https://xn--12080-6ve4g.xn--p1ai/catalog/search?q=x", "dagfarm.ru", DEAL, "ИРИС") is not None


def test_foreign_site_outside_deal_and_app_links_are_not_flagged():
    assert foreign("https://polisorb.com/", "farmiya.ru", DEAL) is None, "сайт бренда — не площадка сделки"
    assert foreign("storefront://kuper.ru/x", "farmiya.ru", DEAL) is None, "app-ссылку не сверяем"
    assert foreign("", "farmiya.ru", DEAL) is None and foreign(None, "farmiya.ru", DEAL) is None
