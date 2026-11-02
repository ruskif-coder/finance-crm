# -*- coding: utf-8 -*-
"""Техобслуживание кабинета паблишеров (владелец 02.11.2026).

Кабинет закрывается, только если при объявлении отмечены «Кабинеты паблишеров». Поломки, которые ловят тесты: кабинет
закрылся при закрытом одном портале (площадки отрезаны без причины); закрытый кабинет пускает на вход или принимает
ответы; закрытый кабинет не может сказать, почему он закрыт (ручка состояния сама попала под заслон); испорченное время
в настройке заперло всех.
"""
from datetime import datetime, timedelta

from app.maintenance import blocks, cabinet_state

NOW = datetime(2026, 11, 2, 12, 0, 0)


def test_portal_only_leaves_the_cabinet_open():
    assert cabinet_state((NOW - timedelta(minutes=1)).isoformat(), "portal", NOW)["mode"] == "off"
    assert cabinet_state(None, None, NOW)["mode"] == "off"


def test_an_announcement_counts_down_then_closes():
    st = cabinet_state((NOW + timedelta(minutes=7)).isoformat(), "portal,cabinet", NOW)
    assert st["mode"] == "announced" and st["seconds_left"] == 420
    assert cabinet_state((NOW - timedelta(seconds=1)).isoformat(), "cabinet", NOW)["mode"] == "active"


def test_a_broken_value_closes_nothing():
    assert cabinet_state("не-дата", "cabinet", NOW)["mode"] == "off"


def test_closed_cabinet_refuses_login_and_answers():
    for path, method in (("/api/login", "POST"), ("/api/tasks", "GET"), ("/api/tasks/5/verdict", "POST"),
                         ("/api/recon/3/answer", "POST")):
        assert blocks(path, method, "active"), path


def test_closed_cabinet_still_explains_itself():
    assert not blocks("/api/maintenance", "GET", "active")
    assert not blocks("/api/health", "GET", "active")


def test_before_the_start_everything_works():
    assert not blocks("/api/tasks/5/verdict", "POST", "announced")
    assert not blocks("/api/login", "POST", "off")
