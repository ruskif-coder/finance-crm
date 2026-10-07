# -*- coding: utf-8 -*-
"""Ссылка в <a href> баннера обязана нести кликовый макрос DSP (05.10.2026).

Загрузчик DSP отклоняет архив, если в любой ссылке нет `{LINK_UNESC}` (код 2051): так упала
первая выгрузка Максавит (режим «обе», в поле диплинка — обычная https-ссылка). Правило
одно: подставлять в href только ссылку с макросом; иначе оставлять макрос DSP — клик идёт
через DSP на посадочную, как у прежних РК Максавит в кабинете DSP.

⚠ 07.10.2026 (хотфикс v2.6.74.3). Макросом считался И `{LINK_ESC}` — на словах документации
«оба только в коде баннера», а не по поведению загрузчика. Загрузчик же требует именно
`{LINK_UNESC}` (его текст: «Any link must contains {LINK_UNESC}»), и SDK-диплинк
`…&primaryTrackingUrl={LINK_ESC}` отклонялся: 16 отказов за 07.10 (4FKFD2 и LBS2QH, 8 креативов).
За всё время журнала DSP не принято ни одной загрузки со ссылкой, где был только `{LINK_ESC}`.
Ссылка с одним `{LINK_ESC}` в href не встаёт: остаётся макрос DSP, клик идёт на веб-посадочную.
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


# Ссылка приложения, в которой есть то, что требует загрузчик: `{LINK_UNESC}`.
APP_UNESC = "maksavit://product/1?track={LINK_UNESC}"


def test_link_with_macro_goes_into_href():
    sdk_unesc = SDK + "&c={LINK_UNESC}"            # в режиме «sdk» из посадочной берётся диплинк deeplink+://
    assert R.click_href({"app_links": "sdk"}, sdk_unesc, None) == sdk_unesc
    assert R.click_href({"app_links": "both"}, WEB, APP_UNESC) == APP_UNESC


@pytest.mark.parametrize("rule", [None, {"app_links": "sdk"}, {"app_links": "both"}])
def test_sdk_deeplink_with_only_the_escaped_macro_stays_out_of_the_banner(rule):
    """Регрессия 07.10.2026 (4FKFD2, LBS2QH): SDK-диплинк из второго поля нёс только
    `{LINK_ESC}`, уходил в href и отклонялся загрузчиком DSP (2051). Нужен `{LINK_UNESC}`."""
    assert R.click_href(rule, WEB, SDK) is None
    assert R.click_href(rule, SDK, None) is None, "то же и для диплинка в посадочной (старые строки)"


def test_warning_when_rule_wanted_a_link_but_it_has_no_macro():
    w = R.click_warning({"app_links": "both"}, WEB, WEB)
    assert w and "макрос" in w
    assert R.click_warning({"app_links": "sdk"}, APP_UNESC, None) is None
    assert R.click_warning(None, WEB, None) is None
    # SDK-диплинк с одним {LINK_ESC} в архив не идёт, но доезжает вторым шагом (`post_upload_href`) —
    # предупреждать не о чем. А ссылка, которая не попадёт в баннер никак, предупреждает.
    assert R.click_warning({"app_links": "sdk"}, WEB, SDK) is None
    w = R.click_warning({"app_links": "both"}, WEB, "maksavit://product/1")
    assert w and "LINK_UNESC" in w, "трафик должен видеть, почему ссылка не встала"


def test_web_mode_is_not_offered_anymore():
    assert "web" not in R.APP_LINKS


def test_app_link_without_macro_is_accepted_but_not_put_into_banner():
    """06.10.2026: ссылка в приложении — своё поле; макрос в ней не обязателен (у
    storefront://… kuper его нет). В баннер она встаёт, только если макрос есть; иначе
    в href остаётся макрос DSP, и это видно предупреждением."""
    assert R.validate_app_link(WEB) == WEB
    assert R.validate_app_link("maksavit://product/1") == "maksavit://product/1"
    assert R.validate_app_link(SDK) == SDK
    assert R.click_href({"app_links": "both"}, WEB, "maksavit://product/1") is None
    assert R.click_warning({"app_links": "both"}, WEB, "maksavit://product/1")


def test_legacy_web_mode_is_saved_as_no_mode():
    """Ревью 05.10.2026: строку со старым «веб» можно пересохранить — режим становится пустым."""
    assert R.normalize_app_links("web") is None
    assert R.normalize_app_links("sdk") == "sdk"
    assert R.normalize_app_links("") is None
