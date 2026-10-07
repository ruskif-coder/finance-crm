# -*- coding: utf-8 -*-
"""Две посадочные у app-площадки (владелец 06.10.2026): веб-ссылка и ссылка в приложении.

  advertiser_url — ВСЕГДА веб (http/https): уходит в ОРД и в link/adomain DSP;
  deeplink_url   — ссылка в приложении: своя схема (storefront://… у kuper), диплинк SDK
                   (deeplink+://…) или тот же https. Может совпадать с веб-ссылкой.

У app-площадки запрос ссылки закрыт, только когда есть ОБЕ.
"""
from types import SimpleNamespace

import pytest

from app.launch_prep import pub_rules as R
from app.routers.launch_prep import url_state

KUPER_APP = "storefront://product_selection/4846"
KUPER_WEB = "https://web.kuper.ru/product-selection/4846-bonduelle123759"
SDK = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9tYWtzYXZpdC5ydS8="
       "&primaryTrackingUrl={LINK_ESC}")


def test_web_field_is_web_only():
    assert R.validate_landing(KUPER_WEB, "app") == KUPER_WEB
    for bad in (KUPER_APP, SDK):
        with pytest.raises(ValueError):
            R.validate_landing(bad, "app")


@pytest.mark.parametrize("good", [KUPER_APP, SDK, KUPER_WEB])
def test_app_field_accepts_app_links_and_web(good):
    assert R.validate_app_link(good) == good


@pytest.mark.parametrize("bad", ["javascript://x", "data://x", "file:///etc", "storefront://",
                                 "просто текст"])
def test_app_field_refuses_garbage(bad):
    with pytest.raises(ValueError):
        R.validate_app_link(bad)


def test_app_field_empty_is_none():
    assert R.validate_app_link("  ") is None


def _m(web=None, app=None, requested=False):
    return SimpleNamespace(advertiser_url=web, deeplink_url=app,
                           url_requested_at="x" if requested else None)


def test_app_surface_needs_both_links():
    assert url_state(_m(KUPER_WEB, None, True), "app") == "запрошена"
    assert url_state(_m(None, KUPER_APP, True), "app") == "запрошена"
    assert url_state(_m(KUPER_WEB, KUPER_APP, True), "app") == "есть"
    assert url_state(_m(KUPER_WEB, KUPER_WEB, True), "app") == "есть", "могут совпадать"


def test_web_surface_needs_web_only():
    assert url_state(_m(KUPER_WEB, None, True), "web") == "есть"
    assert url_state(_m(KUPER_WEB, None, True)) == "есть"


def test_sdk_deeplink_moves_to_app_field_and_goes_to_banner_only_with_unesc_macro():
    """После переноса диплинк SDK живёт в deeplink_url, а веб — в advertiser_url. В баннер он
    встаёт, только если в нём есть `{LINK_UNESC}`; с одним `{LINK_ESC}` загрузчик DSP отклоняет
    весь архив (2051, 07.10.2026: 4FKFD2, LBS2QH) — тогда в href остаётся макрос DSP."""
    assert R.click_href({"app_links": "sdk"}, "https://maksavit.ru/", SDK) is None
    assert R.click_href(None, "https://maksavit.ru/", SDK) is None
    sdk_unesc = SDK + "&c={LINK_UNESC}"
    assert R.click_href({"app_links": "sdk"}, "https://maksavit.ru/", sdk_unesc) == sdk_unesc
    assert R.click_href(None, "https://maksavit.ru/", sdk_unesc) == sdk_unesc


@pytest.mark.parametrize("raw,web,app", [
    (f"{KUPER_WEB} веб {KUPER_APP}", KUPER_WEB, KUPER_APP),
    (SDK, "https://maksavit.ru/", SDK),
    (KUPER_WEB, KUPER_WEB, None),
])
def test_split_legacy_landing(raw, web, app):
    assert R.split_landing(raw) == (web, app)


# ── ревью 06.10.2026 ─────────────────────────────────────────────────────────

def test_web_mode_puts_web_link_into_banner():
    """Режим «веб» — в href веб-ссылка, даже если рядом лежит диплинк SDK. Ссылка встаёт, только
    если в ней есть `{LINK_UNESC}` (загрузчик DSP, хотфикс 07.10.2026); с одним `{LINK_ESC}` — нет."""
    adv = "https://a.ru/x?u={LINK_UNESC}"
    assert R.click_href({"app_links": "web"}, adv, SDK) == adv
    assert R.click_href({"app_links": "web"}, "https://a.ru/x?u={LINK_ESC}", SDK) is None


@pytest.mark.parametrize("bad", ["deeplink+://x\njavascript:alert(1)", "storefront://a b",
                                 "intent://x#Intent;scheme=a;end", "storefront://a\tb"])
def test_app_link_refuses_whitespace_and_intent(bad):
    with pytest.raises(ValueError):
        R.validate_app_link(bad)


def test_split_plan_backfills_app_link_and_reports_conflicts():
    """Перенос: app-пара с одной веб-ссылкой получает её же во второе поле (иначе после
    выкладки откатилась бы с «есть» на «запрошена»); занятое второе поле с ДРУГОЙ ссылкой
    — конфликт, не перезапись."""
    from importlib import import_module
    S = import_module("scripts.2026-10-06_split_app_links")
    web = "https://aptekalegko.ru/x"
    assert S.plan_row(web, None, "app") == (web, web, None)
    assert S.plan_row(web, None, "web") is None
    assert S.plan_row(SDK, None, "app") == ("https://maksavit.ru/", SDK, None)
    w, a, why = S.plan_row(SDK, "storefront://other", "app")
    assert why and "конфликт" in why
    assert S.plan_row(web, "storefront://x", "app") is None, "уже разнесено — не трогаем"
