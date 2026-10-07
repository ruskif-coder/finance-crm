# -*- coding: utf-8 -*-
"""Диплинк SDK попадает в баннер ВТОРЫМ шагом — после загрузки архива (владелец 07.10.2026).

Загрузчик DSP (`Upload.file`) отклоняет архив, если в любой ссылке нет `{LINK_UNESC}` (код 2051), а
SDK-диплинк `deeplink+://navigate?primaryUrl=…&primaryTrackingUrl={LINK_ESC}` его не несёт. Руками его
вписывали в HTML-код креатива уже после загрузки (ручные «инапп»-кампании: apteka25, aptekabv,
Новая аптека, Миницен — статус LAUNCHED), и API `Creative.edit` принимает такую правку (проверено
07.10 на боевом кабинете). Теперь то же делает выгрузка по настройке площадки: режим «sdk»/«обе»
или диплинк SDK в цели пары. Архив при этом остаётся с `{LINK_UNESC}` и проходит загрузчик.

Всё на подставном кабинете: живой DSP здесь не нужен и опасен.
"""
from types import SimpleNamespace as NS

import pytest

from app.dsp import creatives as cr
from app.dsp import provision as prov
from app.dsp.client import MsError
from app.launch_prep import pub_rules as R
from app.launch_prep import sandbox

# фикстура и подставной кабинет — из соседнего теста выгрузки
from tests.test_dsp_provision_once import FakeMs, _camp, _db, _row, wired  # noqa: F401

SDK = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9uZXdhcHRla2EucnUvIyFUb3Zhci83NDMxMTI="
       "&primaryTrackingUrl={LINK_ESC}")
WEB = "https://newapteka.ru/#!Tovar/743112"
BANNER = '<a href="{LINK_UNESC}" target="_blank"><div>баннер</div></a>'


@pytest.fixture
def banner(monkeypatch, wired):          # noqa: F811
    """Загрузчик отдаёт баннер с макросом клика DSP в якоре — как настоящий после `prepare_for_dsp`."""
    monkeypatch.setattr(cr, "upload_zip", lambda c, data, filename=None, local_ref=None:
                        {"html": BANNER, "width": 300, "height": 250, "size": "300x250"})
    return wired


def _sdk_row(rule):
    row = _row(1)
    row["rule"] = rule
    row["target"] = NS(advertiser_url=WEB, deeplink_url=SDK)
    return row


# ── правило: что подставляется после загрузки ───────────────────────────────

@pytest.mark.parametrize("rule", [None, {"app_links": "sdk"}, {"app_links": "both"}])
def test_sdk_deeplink_is_wanted_after_upload(rule):
    assert R.post_upload_href(rule, WEB, SDK) == SDK


def test_nothing_is_wanted_after_upload_for_plain_links():
    assert R.post_upload_href({"app_links": "sdk"}, WEB, WEB) is None
    assert R.post_upload_href(None, WEB, None) is None
    # схема приложения без нашего макроса клика: клики DSP не считались бы, в баннер не ставим
    assert R.post_upload_href({"app_links": "both"}, WEB, "storefront://product_selection/4846") is None


def test_link_with_unesc_macro_goes_through_the_archive_not_the_second_step():
    with_unesc = SDK + "&c={LINK_UNESC}"
    assert R.click_href({"app_links": "sdk"}, WEB, with_unesc) == with_unesc
    assert R.post_upload_href({"app_links": "sdk"}, WEB, with_unesc) is None


def test_no_warning_when_the_deeplink_is_delivered_after_upload():
    assert R.click_warning({"app_links": "sdk"}, WEB, SDK) is None
    # а ссылка, которая в баннер не попадёт никак, по-прежнему предупреждает
    w = R.click_warning({"app_links": "both"}, WEB, "storefront://product_selection/4846")
    assert w and "LINK_UNESC" in w


# ── подстановка в готовый html ──────────────────────────────────────────────

def test_set_html_click_href_replaces_only_the_dsp_macro_anchor():
    html = '<a href="{LINK_UNESC}">x</a><a href="https://terms.example/">условия</a>'
    out, changed = sandbox.set_html_click_href(html, SDK)
    assert changed and f'href="{SDK}"' in out
    assert 'href="https://terms.example/"' in out, "чужую ссылку трогать нельзя"
    assert "{LINK_UNESC}" not in out


def test_set_html_click_href_leaves_a_banner_without_the_macro_alone():
    out, changed = sandbox.set_html_click_href('<a href="https://a.ru/">x</a>', SDK)
    assert not changed and out == '<a href="https://a.ru/">x</a>'


def test_set_html_click_href_cannot_break_out_of_the_attribute():
    out, _ = sandbox.set_html_click_href('<a href="{LINK_UNESC}">x</a>', 'deeplink+://a"onclick="x')
    assert 'onclick="x' not in out.replace("&quot;", "")
    assert out.count('"') == 2


# ── выгрузка: два шага ──────────────────────────────────────────────────────

def test_provision_puts_the_deeplink_in_a_second_edit(banner):
    ms = FakeMs()
    banner["rows"] = [_sdk_row({"app_links": "sdk"})]
    out = prov.provision(_db(), _camp(990501), client=ms)
    assert out["done"] and not out["failed"], out
    assert ms.calls.count("Creative.edit") == 2, "ждали: код креатива, затем диплинк"
    html = ms.cabinet[out["done"][0]["xxhash"]]
    assert f'href="{SDK}"' in html and "{LINK_UNESC}" not in html.split("<a ", 1)[1].split(">", 1)[0]


def test_dsp_refusing_the_deeplink_leaves_a_working_creative_and_a_warning(banner):
    class Strict(FakeMs):
        def creative_edit(self, xx, params, local_ref=None):
            if "deeplink+://" in params["data"]["html_code"]:
                self.calls.append("Creative.edit")
                raise MsError("Creative.edit: Any link must contains {LINK_UNESC} (код 2051)")
            return super().creative_edit(xx, params, local_ref=local_ref)

    ms = Strict()
    banner["rows"] = [_sdk_row({"app_links": "sdk"})]
    out = prov.provision(_db(), _camp(990502), client=ms)
    assert out["done"] and not out["failed"], "отказ диплинка не должен ронять креатив"
    assert "{LINK_UNESC}" in ms.cabinet[out["done"][0]["xxhash"]], "креатив остаётся с макросом DSP"
    assert any("диплинк" in w["warning"] for w in out["warnings"]), out["warnings"]


def test_plain_pair_gets_no_second_edit(banner):
    ms = FakeMs()
    row = _row(1)
    row["rule"] = None
    row["target"] = NS(advertiser_url=WEB, deeplink_url=WEB)
    banner["rows"] = [row]
    out = prov.provision(_db(), _camp(990503), client=ms)
    assert out["done"], out
    assert ms.calls.count("Creative.edit") == 1
