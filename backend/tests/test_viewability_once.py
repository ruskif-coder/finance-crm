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


# 15.11.2026: дизайнер вложил viewability.js в архив баннера, загрузчик DSP добавил свой — в креативе два скрипта, скрипт DSP
# рисует две плашки ЕРИД, и у части баннеров (Изопринозин WTFANV) плашка без стилей уходит под фон. Оставляем последний —
# тот, что после настроек кампании `window.adsn.viewability = {...}`.
DOUBLE = ('<html><head><title>B</title>'
          '<script type="text/javascript" src="https://cdn.example/engine/viewability.js"></script>'
          '<script type="text/javascript">window.adsn={};window.adsn.viewability={"cr_id":"{CR_ID}"};</script>'
          '<script type="text/javascript" src="https://cdn.example/engine/viewability.js"></script>'
          '</head><body><a href="{LINK_UNESC}">x</a></body></html>')


def test_dedupe_keeps_the_last_counter_after_campaign_settings():
    new, changed = cr.dedupe_viewability(DOUBLE)
    assert changed and new.count("viewability.js") == 1
    assert new.index("window.adsn.viewability") < new.index("viewability.js")


def test_dedupe_leaves_a_single_counter_alone():
    assert cr.dedupe_viewability(DSP_HTML) == (DSP_HTML, False)
    assert cr.dedupe_viewability(BARE) == (BARE, False)


def test_dedupe_matches_counter_with_query_and_other_quotes():
    html = DOUBLE.replace('viewability.js"></script><script type="text/javascript">',
                          "viewability.js?cid=1'></script><script type=\"text/javascript\">", 1)
    html = html.replace('src="https://cdn.example/engine/viewability.js?cid=1\'', "src='https://cdn.example/engine/viewability.js?cid=1'", 1)
    new, changed = cr.dedupe_viewability(html)
    assert changed and new.count("viewability.js") == 1


def test_wrap_removes_a_double_counter_from_the_banner():
    out = cr.wrap_html(DOUBLE, erid="K1", viewability_src=SRC)
    assert out.count("viewability.js") == 1
