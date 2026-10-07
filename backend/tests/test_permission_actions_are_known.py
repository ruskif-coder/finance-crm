# -*- coding: utf-8 -*-
"""Каждое действие в проверках прав — из `ACTION_FIELDS`.

`require_permission(section, "edti")` молча означал бы «просмотр»: `ACTION_FIELDS.get(action,
"can_view")` подставлял чтение вместо опечатки, и ручка записи открывалась по праву чтения
(внешний аудит 06.10.2026). Сегодня все названия верны — это заряд, не взрыв. Прибор ставит
запрет: фабрики прав падают при ОПИСАНИИ ручки (при старте), а не открывают её молча.
"""
import pytest

from app.main import app
from app.permissions import ACTION_FIELDS, require_any_permission, require_permission
from tests.route_utils import iter_dependencies


def test_every_action_used_by_a_route_is_known():
    used = {}
    for route in app.routes:
        dep = getattr(route, "dependant", None)
        if dep is None:
            continue
        for d in iter_dependencies(dep):
            act = getattr(d.call, "_perm_action", None)
            if act is not None:
                used.setdefault(act, []).append(getattr(route, "path", "?"))
    unknown = {a: p[:3] for a, p in used.items() if a not in ACTION_FIELDS}
    assert not unknown, f"действие не из ACTION_FIELDS: {unknown}"


def test_a_typo_in_the_action_fails_when_the_route_is_declared():
    with pytest.raises(ValueError):
        require_permission("operations", "edti")
    with pytest.raises(ValueError):
        require_any_permission([("operations", "edti")])


def test_known_actions_still_build():
    for a in ACTION_FIELDS:
        require_permission("operations", a)
