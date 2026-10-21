# -*- coding: utf-8 -*-
"""Ручной перевод стадий (владелец 14.10.2026): через стадию — только мастер; срыв — только в терминал своего этапа."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.sales import stage_move as SM

S = {i: SimpleNamespace(id=i, name=n, phase_id=p, is_terminal=t, is_lost=l) for i, n, p, t, l in [
    (1, "МП Подготовка", 1, False, False), (2, "МП Отправлено", 1, False, False), (3, "Сделка не случилась", 1, True, True),
    (5, "Бронь", 2, False, False), (6, "Готовятся к старту", 2, False, False), (7, "В размещении", 2, False, False),
    (9, "Сделка сорвалась", 2, True, True), (10, "Подготовка ДС", 3, False, False)]}
ORDER = [1, 2, 5, 6, 7, 10]


class Cat:
    by_id = S

    def is_before(self, a, b):
        return a in ORDER and b in ORDER and ORDER.index(a) < ORDER.index(b)


def _guard(monkeypatch, cur, target, master=False):
    monkeypatch.setattr(SM, "next_stage", lambda db, d, c: S[ORDER[ORDER.index(cur) + 1]] if cur in ORDER[:-1] else None)
    monkeypatch.setattr(SM, "is_master", lambda u: master)
    return SM.manual_guard(None, SimpleNamespace(our_stage_id=cur), S[target], None, Cat())


def test_next_stage_is_free_skip_needs_master(monkeypatch):
    assert _guard(monkeypatch, 5, 6) is None
    assert "только мастер" in _guard(monkeypatch, 5, 7)
    assert _guard(monkeypatch, 5, 7, master=True) is None
    assert _guard(monkeypatch, 7, 5) is None                     # назад — своё правило в вызывающем (мастер)


def test_lost_only_into_own_phase_terminal_even_for_master(monkeypatch):
    assert _guard(monkeypatch, 2, 3) is None                     # Песочница → «не случилась»
    assert "Сделка не случилась" in _guard(monkeypatch, 2, 9, master=True)
    assert _guard(monkeypatch, 6, 9) is None                     # реализация → «сорвалась»
    assert "Сделка сорвалась" in _guard(monkeypatch, 6, 3)
    assert "документооборот" in _guard(monkeypatch, 10, 9, master=True)   # в ДО срыва нет
