# -*- coding: utf-8 -*-
"""Тихие часы по умолчанию 22:00–08:00 МСК — у тех, кто своих не задал (владелец 21.10.2026: «все 3 да»).

Замер на копии прода: тихие часы заданы у двоих из шести сотрудников с ботом, сканер работает круглые сутки, и в 00:20 МСК
четверо получали напоминания. Свои часы человека главнее умолчания; одинаковые «с» и «по» — «без тихих часов»;
события «нельзя отключить» по-прежнему проходят сквозь тихие часы."""
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import pytest

from app.notify import channels as C

EV = SimpleNamespace(locked=False)


def _at(h):
    return mock.patch.object(C.timez, "msk_now", lambda: datetime(2026, 10, 21, h, 20))


@pytest.mark.parametrize("ch,hour,quiet", [
    (None, 0, True), (None, 7, True), (None, 8, False), (None, 21, False), (None, 22, True),      # нет строки настроек
    (SimpleNamespace(mute_until=None, quiet_from=None, quiet_to=None), 0, True),                  # строка есть, часов нет
    (SimpleNamespace(mute_until=None, quiet_from=19, quiet_to=23), 0, False),                     # свои часы главнее
    (SimpleNamespace(mute_until=None, quiet_from=19, quiet_to=23), 20, True),
    (SimpleNamespace(mute_until=None, quiet_from=0, quiet_to=0), 0, False),                       # «без тихих часов»
])
def test_default_quiet_hours(ch, hour, quiet):
    with _at(hour):
        assert C.quiet_now(ch, EV) is quiet


def test_locked_events_still_pass():
    with _at(0):
        assert C.quiet_now(None, SimpleNamespace(locked=True)) is False
