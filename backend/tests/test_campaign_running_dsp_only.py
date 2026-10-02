# -*- coding: utf-8 -*-
"""РК «запущена» — только когда крутит площадка НАШЕЙ DSP (владелец 02.10.2026, 37ZTY3).

Adfox-площадки отмечают «запущен» вручную; РК от этого становилась «запущенной», и кнопка
старта в строке гасла, хотя ни одна площадка DSP не запущена. Adfox «не в счёт».
"""
import inspect
from types import SimpleNamespace

import app.main  # noqa: F401
from app.routers import traffic_dashboard as td

C = SimpleNamespace(plan_show=1000)


def test_running_adfox_placement_does_not_make_campaign_running():
    cr = {1: [{"status": "согласован", "ms_creative_xxhash": None}],      # Adfox, руками «запущен»
          2: [{"status": "согласован", "ms_creative_xxhash": "AB"}]}      # наша DSP, ждёт запуска
    assert td._chain_of(C, [(1, "запущен"), (2, "ждёт запуска")], cr) == "готова"


def test_running_dsp_placement_makes_campaign_running():
    cr = {2: [{"status": "согласован", "ms_creative_xxhash": "AB"}]}
    assert td._chain_of(C, [(2, "запущен")], cr) == "запущена"


def test_dashboard_list_uses_the_same_rule():
    assert "_uploaded_placements(" in inspect.getsource(td.dashboard)


def test_launch_hint_names_every_lock():
    h = td.launch_hint
    assert h(None, None, False, ready=2, running=0) is None
    assert "DSP" in h("Площадки ещё не выгружены в DSP", None, False, 0, 0)
    assert "объём" in h(None, {"blocked": True, "message": "объёмы 2 млн больше плана 1 млн"}, False, 2, 0)
    assert "архиве" in h(None, None, True, 2, 0)
    assert "3 ждут" in h(None, None, False, ready=0, running=0, waiting=3)
    assert h(None, None, False, ready=0, running=1) is None, "крутит — пауза доступна"


def test_detail_rows_carry_start_why():
    src = inspect.getsource(td.campaign)
    assert '"start_why"' in src and "launch_hint(" in src
    assert "launch_hint(" in inspect.getsource(td.dashboard)
