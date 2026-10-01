# -*- coding: utf-8 -*-
"""Пиксель и кликовая ссылка Weborama в DSP (владелец 01.10.2026): пиксель — ТОЛЬКО полем
`pixel`; домен в `a.ycp` — кириллицей. Кликовый счётчик в DSP не ставим (01.10.2026)."""
from types import SimpleNamespace as NS
from urllib.parse import unquote

from app.dsp import creatives as cr
from app.dsp import provision as P
from app.weborama import naming

IMP = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=im&a.si=10419&a.te=643"
       "&a.he=~HEIGHT~&a.wi=~WIDTH~&a.hr=p&a.ra=[RANDOM]")


def _row(domain, click=None):
    return {"placement": NS(weborama_pixel=IMP, weborama_click=click),
            "publisher": NS(domain=domain)}


def test_pixel_has_cyrillic_domain_size_and_erid():
    url = P.pixel_url(_row("009.рф"), 240, 400, None, "ERID1")
    assert unquote(url).endswith("a.ra={RND}&a.ycp=https://009.рф")
    assert url.isascii(), "голая кириллица наружу не уходит (28.09 её не приняли)"
    assert "a.wi=240" in url and "a.he=400" in url and "[RANDOM]" not in url


def test_latin_domain_unchanged():
    assert naming.final_tag(IMP, "farmakopeika.ru").endswith("a.ycp=https://farmakopeika.ru")


def test_pixel_goes_to_field():
    p = cr.build_creative_params(title="t", link="https://a.ru", pixel="https://px")
    assert p["pixel"] == "https://px"
    assert "pixel" not in cr.build_creative_params(title="t", link="https://a.ru")


def test_adaptive_banner_gets_zero_size_not_placeholder():
    """0×0 адаптивного — в теге `a.wi=0&a.he=0`, не `~WIDTH~` (регрессия v2.6.57)."""
    url = P.pixel_url(_row("a.ru"), 0, 0, None, None)
    assert "a.wi=0" in url and "a.he=0" in url and "~WIDTH~" not in url
