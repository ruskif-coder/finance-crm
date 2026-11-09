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


def test_stretched_link_does_not_cover_the_erid_plate():
    """Ломается, если вернуть обёртке верхний слой (`z-index`): она ляжет поверх плашки ЕРИД, и клик по плашке уйдёт на посадочную
    вместо сведений о рекламодателе (09.11.2026, все креативы)."""
    out = cr.wrap_html(DSP_HTML)
    style = out[out.index(cr.CLICK_FIX_MARK):out.index("</style>")]
    assert "z-index" not in style


def test_restyle_replaces_any_old_click_fix_style_once():
    """Ломается, если перевыгрузка ищет только старый текст стиля: у RLXATY-KOP-cr2 стиль заменён руками на вариант с классом
    `.simb-click-fix` — его тоже надо привести к новому, и ровно одним блоком."""
    old = DSP_HTML.replace("</head>", '<style data-simb-click-fix>body>a{display:block;position:absolute;inset:0;'
                                      'z-index:2147483000;cursor:pointer}</style></head>')
    by_hand = DSP_HTML.replace("</head>", '<style data-simb-click-fix>.simb-click-fix{display:block}</style></head>')
    for html in (old, by_hand):
        new, changed = cr.restyle_click_fix(html)
        assert changed
        assert new.count("data-simb-click-fix") == 1
        assert '<style data-simb-click-fix>body>a{display:block;position:absolute;inset:0;cursor:pointer}</style>' in new
        assert 'href="{LINK_UNESC}"' in new


def test_restyle_leaves_current_and_unmarked_html_alone():
    assert cr.restyle_click_fix(cr.wrap_html(DSP_HTML)) == (cr.wrap_html(DSP_HTML), False)
    assert cr.restyle_click_fix(DSP_HTML) == (DSP_HTML, False)
