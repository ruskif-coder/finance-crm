# -*- coding: utf-8 -*-
"""Посадочная app-площадки в формате диплинка SDK (владелец 02.10.2026).

`deeplink+://navigate?primaryUrl=<base64 https>&primaryTrackingUrl={LINK_ESC}`:
строка целиком — в `<a href>` баннера (макрос `{LINK_ESC}` DSP подставляет только в коде
баннера), а в `link`/`adomain` DSP, ОРД и всё, где нужен веб-адрес, — раскодированный
`primaryUrl`. На web-поверхности — по-прежнему только http(s).
"""
import pytest

from app.launch_prep import pub_rules as R

MINICEN = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9taW5pY2VuLnJ1LyMhVG92YXIvNzE3NjA5"
           "&primaryTrackingUrl={LINK_ESC}")
NEWAPT = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9uZXdhcHRla2EucnUvIyFUb3Zhci83NDMxMTI="
          "&primaryTrackingUrl={LINK_ESC}")


def test_web_url_is_decoded_from_primary_url():
    assert R.web_url(MINICEN) == "https://minicen.ru/#!Tovar/717609"
    assert R.web_url(NEWAPT) == "https://newapteka.ru/#!Tovar/743112"
    assert R.web_url("https://maksavit.ru/catalog/144666/") == "https://maksavit.ru/catalog/144666/"
    assert R.web_url(None) is None


def test_app_landing_accepted_only_on_app_surface():
    assert R.validate_landing(MINICEN, "app") == MINICEN
    with pytest.raises(ValueError, match="app"):
        R.validate_landing(MINICEN, "web")
    assert R.validate_landing("https://b-apteka.ru/x", "web") == "https://b-apteka.ru/x"
    assert R.validate_landing("  ", "app") is None


@pytest.mark.parametrize("bad", [
    "deeplink+://navigate?primaryTrackingUrl={LINK_ESC}",                 # нет primaryUrl
    "deeplink+://navigate?primaryUrl=!!!не-base64",                       # не раскодировать
    "deeplink+://navigate?primaryUrl=amF2YXNjcmlwdDphbGVydCgxKQ==",       # javascript:alert(1)
    "maksavit://catalog/1",                                               # чужая схема
    "javascript:alert(1)",
])
def test_bad_landing_is_refused(bad):
    with pytest.raises(ValueError):
        R.validate_landing(bad, "app")


def test_href_gets_the_whole_deeplink_link_gets_web():
    assert R.click_href({"app_links": "web"}, MINICEN, None) == MINICEN
    assert R.click_href(None, MINICEN, None) == MINICEN, "диплинк без правила площадки потерялся бы"
    assert R.click_href(None, "https://a.ru/", None) is None
    assert R.click_href({"app_links": "both"}, MINICEN, None) == MINICEN


def test_deeplink_in_landing_satisfies_both_mode():
    assert R.pair_problem({"app_links": "both"}, MINICEN, None) is None
    assert R.pair_problem({"app_links": "both"}, "https://a.ru/", None)


def test_dsp_and_ord_use_web_address():
    import inspect
    from app.dsp import provision, targeting_creative
    from app.routers import launch_prep
    assert "web_url(" in inspect.getsource(provision)
    assert "web_url(" in inspect.getsource(targeting_creative)
    assert "web_url(" in inspect.getsource(launch_prep._ord_urls) if hasattr(launch_prep, "_ord_urls") \
        else "web_url(" in inspect.getsource(launch_prep)
