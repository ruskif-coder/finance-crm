# -*- coding: utf-8 -*-
"""Виза медиаплана (владелец 15.10.2026): две «проверено» в конструкторе визируют план; созданный системой — без визы."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.routers import media_plans as MP
from app.sales import stage_checks as SC


def test_save_with_both_checks_marks_the_plan():
    p = SimpleNamespace(verified_at=None, verified_by=None)
    MP._mark_verified(p, SimpleNamespace(verified=True), SimpleNamespace(id=4))
    assert p.verified_at is not None and p.verified_by == 4
    q = SimpleNamespace(verified_at=None, verified_by=None)
    MP._mark_verified(q, SimpleNamespace(verified=None), SimpleNamespace(id=4))
    assert q.verified_at is None                                   # без отметок — не виза


def test_check_reads_the_plan_visa():
    fn = SC.REGISTRY["mp_verified"].fn
    assert fn(SimpleNamespace(plan=None)).state == SC._na().state                     # нет плана — ловит «МП привязан»
    assert fn(SimpleNamespace(plan=SimpleNamespace(verified_at=None))).blocks         # создан системой
    assert not fn(SimpleNamespace(plan=SimpleNamespace(verified_at=1))).blocks
