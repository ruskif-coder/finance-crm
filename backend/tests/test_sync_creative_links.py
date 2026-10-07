# -*- coding: utf-8 -*-
"""Скрипт `2026-10-07_sync_creative_links`: приводит уже заведённые креативы DSP к правилам ссылок.

Править такие креативы раньше приходилось вручную по просьбе (диплинк SDK в `<a href>`, якорь в
«Конечном URL»). Здесь проверяется ПЛАН правок — чистая функция; сам обмен с DSP — как у выгрузки
(подставной кабинет в test_dsp_app_deeplink_after_upload.py).
"""
import importlib

import pytest

M = importlib.import_module("scripts.2026-10-07_sync_creative_links")

SDK = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9uZXdhcHRla2EucnUvIyFUb3Zhci83NDMxMTI="
       "&primaryTrackingUrl={LINK_ESC}")
WEB = "https://newapteka.ru/#!Tovar/743112"
HTML = '<body><a href="{LINK_UNESC}" target="_blank"><div>баннер</div></a></body>'


def _info(html=HTML, adomain="https://newapteka.ru/", status="STOPPED"):
    return {"status": status, "adomain": adomain, "link": WEB, "data": {"html_code": html}}


def test_sdk_pair_wants_the_deeplink_and_the_full_final_url():
    plan = M.plan_edits({"app_links": "sdk"}, WEB, SDK, _info())
    assert set(plan) == {"html", "adomain"}
    assert f'href="{SDK}"' in plan["html"] and "{LINK_UNESC}" not in plan["html"]
    assert plan["adomain"] == WEB, "«Конечный URL» с якорем — как кликовая ссылка"


def test_second_run_changes_nothing():
    first = M.plan_edits({"app_links": "sdk"}, WEB, SDK, _info())
    done = _info(html=first["html"], adomain=first["adomain"])
    assert M.plan_edits({"app_links": "sdk"}, WEB, SDK, done) == {}


def test_plain_pair_is_left_alone_when_it_already_follows_the_rule():
    assert M.plan_edits(None, WEB, WEB, _info(adomain=WEB)) == {}


def test_plain_pair_gets_only_the_final_url_fixed():
    plan = M.plan_edits(None, "https://aptekabv.ru/tovar/743112", "https://aptekabv.ru/tovar/743112",
                        _info(adomain=""))
    assert plan == {"adomain": "https://aptekabv.ru/tovar/743112"}


def test_banner_without_the_dsp_macro_is_not_touched():
    plan = M.plan_edits({"app_links": "sdk"}, WEB, SDK,
                        _info(html='<a href="https://a.ru/">x</a>', adomain=WEB))
    assert plan == {}, "нет якоря с макросом DSP — подставлять некуда, чужие ссылки не трогаем"


def test_script_has_a_dry_run_by_default(capsys):
    assert M.main([]) == 2             # без кодов сделок — справка, ничего не делаем
    assert "--apply" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["Новая аптека", "aptekabv.ru", ""])
def test_backup_file_name_is_safe(name):
    assert "/" not in M._slug(name) and " " not in M._slug(name)
