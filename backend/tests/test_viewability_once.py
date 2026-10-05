# -*- coding: utf-8 -*-
"""Счётчик видимости в креативе — ровно один (владелец 05.10.2026).

Загрузчик DSP сам вставляет `viewability.js` с параметрами кампании и креатива, а наша
обёртка вшивала второй — без параметров и раньше DSP-шного. Правило: если в HTML от
загрузчика счётчик уже есть — свой не ставим; если нет — ставим свой, и это проверка того,
что счётчик в креативе есть всегда."""
from app.dsp import creatives as cr

SRC = "https://cdn.example/engine/viewability.js"
DSP_HTML = ('<html><head><script type="text/javascript">window.adsn={};</script>'
            '<script type="text/javascript" src="https://cdn.example/engine/viewability.js">'
            '</script></head><body><a href="{LINK_UNESC}">x</a></body></html>')
BARE = '<html><head></head><body><a href="{LINK_UNESC}">x</a></body></html>'


def test_dsp_counter_present_ours_not_added():
    out = cr.wrap_html(DSP_HTML, erid="K1", viewability_src=SRC)
    assert out.count("viewability.js") == 1
    assert '<meta name="erid" content="K1">' in out


def test_dsp_counter_missing_ours_added():
    out = cr.wrap_html(BARE, viewability_src=SRC)
    assert out.count("viewability.js") == 1


def test_no_setting_no_counter_added():
    assert cr.wrap_html(BARE).count("viewability.js") == 0


def test_dsp_counter_with_query_is_recognized():
    """Ревью 05.10.2026: счётчик DSP с параметрами в адресе тоже считается поставленным."""
    html = DSP_HTML.replace("viewability.js\"", "viewability.js?cid=1&cr=2\"")
    assert cr.wrap_html(html, viewability_src=SRC).count("viewability.js") == 1
