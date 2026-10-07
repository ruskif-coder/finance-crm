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
    """С 06.10.2026 диплинк — во втором поле (ссылка в приложении); веб-поле — только http(s)."""
    assert R.validate_app_link(MINICEN) == MINICEN
    with pytest.raises(ValueError, match="второе поле"):
        R.validate_landing(MINICEN, "app")
    with pytest.raises(ValueError):
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


def test_href_gets_the_whole_deeplink_only_when_it_carries_the_unesc_macro():
    """Диплинк целиком в href — только с `{LINK_UNESC}` (хотфикс 07.10.2026): загрузчик DSP
    отклоняет ссылку с одним `{LINK_ESC}` (2051). Без него — макрос DSP, в `link` веб-адрес."""
    minicen_u = MINICEN + "&c={LINK_UNESC}"
    assert R.click_href({"app_links": "web"}, minicen_u, None) == minicen_u
    assert R.click_href(None, minicen_u, None) == minicen_u, "диплинк без правила площадки потерялся бы"
    assert R.click_href({"app_links": "both"}, minicen_u, None) == minicen_u
    assert R.click_href(None, "https://a.ru/", None) is None
    for rule in (None, {"app_links": "web"}, {"app_links": "both"}):
        assert R.click_href(rule, MINICEN, None) is None, "только {LINK_ESC} — DSP отклонит архив"


def test_deeplink_in_landing_satisfies_both_mode():
    assert R.pair_problem({"app_links": "both"}, MINICEN, None) is None
    assert R.pair_problem({"app_links": "both"}, "https://a.ru/", None)


def test_dsp_and_ord_use_web_address():
    import inspect
    from app.dsp import provision, targeting_creative
    from app.launch_prep import erid_service
    assert "web_url(" in inspect.getsource(provision)
    assert "web_url(" in inspect.getsource(targeting_creative)
    # Адреса для ОРД собирает выпуск ЕРИД — сервис `erid_service` (02.10.2026).
    assert "web_url(" in inspect.getsource(erid_service._target_urls)


def test_dsp_link_has_cyrillic_host_like_adomain():
    """link и adomain креатива — одним правилом (владелец 02.10.2026): посадочная, вписанная
    в punycode, уходила в link как есть, а adomain — кириллицей."""
    from app.dsp import creatives as CR
    u = "https://xn--12080-6ve4g.xn--p1ai/catalog/product/lioton-1000-gel-100-g"
    assert CR.landing_link(u) == "https://120на80.рф/catalog/product/lioton-1000-gel-100-g"
    assert CR.landing_link(u) == CR.landing_adomain(u)
    assert CR.landing_link("https://a.ru/x?y=1") == CR.landing_adomain("https://a.ru/x?y=1")
    import inspect
    from app.dsp import provision
    assert "landing_link(" in inspect.getsource(provision)


def test_dsp_link_keeps_spa_anchor():
    from app.dsp import creatives as CR
    assert CR.landing_link("https://minicen.ru/#!Tovar/717609") == "https://minicen.ru/#!Tovar/717609"


def test_dsp_link_long_url_is_not_cut_to_domain_and_anchor_encoded():
    from app.dsp import creatives as CR
    long = "https://xn--12080-6ve4g.xn--p1ai/" + "a" * 1100
    assert CR.landing_link(long).startswith("https://120на80.рф/aaa"), "ссылку не урезаем до домена"
    assert CR.landing_adomain(long) == "https://120на80.рф/"
    assert CR.landing_link("https://a.ru/#!Товар 1") == "https://a.ru/#!%D0%A2%D0%BE%D0%B2%D0%B0%D1%80%201"
    assert "#" not in CR.landing_adomain("https://minicen.ru/#!Tovar/717609")
