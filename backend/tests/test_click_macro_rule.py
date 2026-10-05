# -*- coding: utf-8 -*-
"""Ссылка в <a href> баннера обязана нести кликовый макрос DSP (05.10.2026).

Загрузчик DSP отклоняет архив, если в любой ссылке нет `{LINK_UNESC}` (код 2051): так упала
первая выгрузка Максавит (режим «обе», в поле диплинка — обычная https-ссылка). Правило
одно: подставлять в href только ссылку с макросом; иначе оставлять макрос DSP — клик идёт
через DSP на посадочную, как у прежних РК Максавит в кабинете DSP.
"""
import pytest

from app.launch_prep import pub_rules as R

WEB = "https://maksavit.ru/catalog/144666/"
SDK = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9tYWtzYXZpdC5ydS8="
       "&primaryTrackingUrl={LINK_ESC}")


@pytest.mark.parametrize("rule,adv,deep", [
    ({"app_links": "both"}, WEB, WEB),                      # случай LBS2QH × Максавит
    ({"app_links": "both"}, WEB, "maksavit://product/1"),   # схема приложения без макроса
    ({"app_links": "web"}, WEB, None),                      # старый режим «веб»
])
def test_link_without_macro_never_replaces_dsp_macro(rule, adv, deep):
    assert R.click_href(rule, adv, deep) is None


def test_link_with_macro_goes_into_href():
    assert R.click_href({"app_links": "sdk"}, SDK, None) == SDK
    assert R.click_href({"app_links": "both"}, WEB, SDK) == SDK


def test_warning_when_rule_wanted_a_link_but_it_has_no_macro():
    w = R.click_warning({"app_links": "both"}, WEB, WEB)
    assert w and "макрос" in w
    assert R.click_warning({"app_links": "sdk"}, SDK, None) is None
    assert R.click_warning(None, WEB, None) is None


def test_web_mode_is_not_offered_anymore():
    assert "web" not in R.APP_LINKS


def test_deeplink_without_macro_is_refused():
    with pytest.raises(ValueError, match="макрос"):
        R.validate_deeplink(WEB)
    with pytest.raises(ValueError, match="макрос"):
        R.validate_deeplink("maksavit://product/1")
    assert R.validate_deeplink(SDK) == SDK
    assert R.validate_deeplink("") is None


def test_legacy_web_mode_is_saved_as_no_mode():
    """Ревью 05.10.2026: строку со старым «веб» можно пересохранить — режим становится пустым."""
    assert R.normalize_app_links("web") is None
    assert R.normalize_app_links("sdk") == "sdk"
    assert R.normalize_app_links("") is None
