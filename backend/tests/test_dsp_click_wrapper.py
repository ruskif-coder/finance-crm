# -*- coding: utf-8 -*-
"""Клик по всей площади баннера (14.10.2026, сделка 9E8Z4U): загрузчик DSP заменяет ссылку баннера своей обёрткой
`<a href="{LINK_UNESC}">` без класса. Баннер, свёрстанный под Adfox (`<a class="banner">` блоком на весь экран, слои без мыши),
остаётся с обёрткой нулевого размера — показы есть, кликнуть некуда. Обёртку растягиваем на весь баннер стилем."""
from app.dsp import creatives as cr

DSP_HTML = ('<!doctype html><html><head><meta name="ad.size" content="width=0,height=0"></head>\n'
            '<body><a href="{LINK_UNESC}" target="_blank" style="cursor:pointer">\n<section class="scene"></section>\n</a></body></html>')


def test_wrapper_link_is_stretched_over_the_whole_banner():
    out = cr.wrap_html(DSP_HTML)
    assert cr.CLICK_FIX_MARK in out
    head = out[:out.index("</head>")]
    assert "body>a{display:block;position:absolute;inset:0" in head.replace(" ", "")
    assert out.count('href="{LINK_UNESC}"') == 1                       # макрос клика не тронут


def test_fix_is_added_once_and_not_without_the_dsp_wrapper():
    once = cr.wrap_html(DSP_HTML)
    assert cr.wrap_html(once).count(cr.CLICK_FIX_MARK) == 1
    plain = '<html><head></head><body><div>нет обёртки</div></body></html>'
    assert cr.CLICK_FIX_MARK not in cr.wrap_html(plain, erid="E1")
