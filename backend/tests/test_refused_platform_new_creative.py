# -*- coding: utf-8 -*-
"""Отказ площадки не запирает отправку нового креатива (владелец 21.10.2026): добавленная в креатив, она в списке получателей,
а отправка снимает отказ — у неё снова живой креатив без ответа (иначе её согласие не сдвинуло бы состояние)."""
from types import SimpleNamespace as NS

from app.routers import launch_prep as LP


def test_refused_target_reopens_when_given_new_creative():
    t = NS(state="отказ площадки")
    assert LP.reopen_refused(t) is True and t.state == "согласование"


def test_other_states_untouched():
    for st in ("согласование", "согласован", "в размещении", "ерид получен"):
        t = NS(state=st)
        assert LP.reopen_refused(t) is False and t.state == st


def test_reopen_button_uses_the_same_rule():
    import inspect
    assert "reopen_refused(t)" in inspect.getsource(LP.reopen_target)


def test_set_recipients_do_not_drop_refused():
    import inspect
    assert "отказ площадки" not in inspect.getsource(LP._targets_for_set)


def test_send_lifts_refusal_and_adding_does_not():
    import inspect
    assert "reopen_refused(t)" in inspect.getsource(LP.send_set)
    assert "reopen_refused" not in inspect.getsource(LP._attach)
