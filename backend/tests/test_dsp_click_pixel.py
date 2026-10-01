# -*- coding: utf-8 -*-
"""Пиксель и кликовая ссылка Weborama в DSP (владелец 01.10.2026): пиксель — ТОЛЬКО полем
`pixel`; конечный URL — кликовый счётчик с посадочной в `g.lu`; домен в `a.ycp` — кириллицей."""
from types import SimpleNamespace as NS
from urllib.parse import unquote

from app.dsp import creatives as cr
from app.dsp import provision as P
from app.weborama import naming

IMP = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=im&a.si=10419&a.te=643"
       "&a.he=~HEIGHT~&a.wi=~WIDTH~&a.hr=p&a.ra=[RANDOM]")
CLICK = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=cl&a.si=10419&a.te=643"
         "&erid=[ERID_ID]&er=[ERID_VALUE]&a.ra=[RANDOM]&g.lu=")


def _row(domain, click=CLICK):
    return {"placement": NS(weborama_pixel=IMP, weborama_click=click),
            "publisher": NS(domain=domain)}


def test_pixel_has_cyrillic_domain_size_and_erid():
    url = P.pixel_url(_row("009.рф"), 240, 400, None, "ERID1")
    assert unquote(url).endswith("a.ra={RND}&a.ycp=https://009.рф")
    assert url.isascii(), "голая кириллица наружу не уходит (28.09 её не приняли)"
    assert "a.wi=240" in url and "a.he=400" in url and "[RANDOM]" not in url


def test_latin_domain_unchanged():
    assert naming.final_tag(IMP, "farmakopeika.ru").endswith("a.ycp=https://farmakopeika.ru")


def test_click_link_wraps_landing_and_erid():
    land = "https://009.xn--p1ai/search/x?region=false&a=1"
    link = P.click_link(_row("009.рф"), land, "ERID1")
    assert link.startswith(CLICK.split("&erid")[0]) and "a.A=cl" in link
    assert "erid=ERID1&er=ERID1" in link and "a.ra={RND}" in link
    assert unquote(link.split("&g.lu=")[1]) == land, "посадочная целиком, закодирована"


def test_no_click_stays_landing():
    assert P.click_link(_row("a.ru", click=None), "https://a.ru/p", "E") == "https://a.ru/p"


def test_pixel_goes_to_field():
    p = cr.build_creative_params(title="t", link="https://a.ru", pixel="https://px")
    assert p["pixel"] == "https://px"
    assert "pixel" not in cr.build_creative_params(title="t", link="https://a.ru")


def test_adaptive_banner_gets_zero_size_not_placeholder():
    """0×0 адаптивного — в теге `a.wi=0&a.he=0`, не `~WIDTH~` (регрессия v2.6.57)."""
    url = P.pixel_url(_row("a.ru"), 0, 0, None, None)
    assert "a.wi=0" in url and "a.he=0" in url and "~WIDTH~" not in url
