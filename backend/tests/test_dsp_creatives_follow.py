# -*- coding: utf-8 -*-
"""Креативы в DSP следуют запуску площадки (владелец 28.09.2026)."""
import inspect

from app.dsp import campaigns as C

ROWS = [("AAA", "запущен", "согласован"), ("BBB", "ждёт запуска", "согласован"),
        ("CCC", "запущен", "у площадки"), ("DDD", "запущен", "отклонён"), (None, "запущен", "согласован")]


def test_launch_turns_on_only_agreed_creatives_of_started_placements():
    assert C.creative_targets(ROWS, "LAUNCHED") == {"AAA": "LAUNCHED", "BBB": "STOPPED",
                                                    "CCC": "STOPPED"}


def test_stop_stops_all_but_never_touches_withdrawn():
    assert C.creative_targets(ROWS, "STOPPED") == {"AAA": "STOPPED", "BBB": "STOPPED",
                                                   "CCC": "STOPPED"}
    assert C.creative_targets(ROWS, "ARCHIVE") == {}


def test_campaign_status_drives_creatives():
    assert "follow_creatives(" in inspect.getsource(C.apply_status)
