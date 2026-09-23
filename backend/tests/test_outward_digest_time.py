# -*- coding: utf-8 -*-
"""Прибор: час события в дайджесте площадке — московский.

`cabinet_digest_queue.created_at` лежит в UTC. Карточка печатала его как есть, и
площадка читала «06:14» о событии, случившемся у неё в 09:14 (аудит 23.09.2026).
"""
from datetime import datetime
from types import SimpleNamespace

from app.notify.outward.digest import _card


def test_card_time_is_moscow():
    r = SimpleNamespace(title="t", body="b", link_abs="", tone=None, tag=None, context=None,
                        created_at=datetime(2026, 9, 23, 6, 14), facts=None)
    assert _card(r)["when"] == "09:14"


def test_card_without_time_is_empty():
    r = SimpleNamespace(title="t", body="b", link_abs="", tone=None, tag=None, context=None,
                        created_at=None, facts=None)
    assert _card(r)["when"] == ""
