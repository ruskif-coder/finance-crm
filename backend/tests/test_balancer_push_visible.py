# -*- coding: utf-8 -*-
"""Правка балансировщика: сбой отправки лимитов в DSP виден человеку (ревью 31.10.2026).

С 31.10 правка индекса сразу шлёт лимиты креативов в DSP по каждой РК, где сдвинулся план
площадки. Результат отправки выбрасывался, и ответ говорил «доли в РК пересчитаны», даже если
DSP не принял ни одного лимита: человек уходил с уверенностью, что площадки крутят по-новому.

Поломка, которую ловит тест: итог `push_limits` снова не доходит до ответа ручки.
"""
from types import SimpleNamespace

from app.ad import build, volumes_now
from app.routers import traffic_balancer as TB


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, camps):
        self.camps = camps

    def query(self, *_a):
        return _Query(self.camps)

    def rollback(self):
        pass


def test_failed_limits_reach_the_answer(monkeypatch):
    camps = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    monkeypatch.setattr(build, "refresh_weights",
                        lambda db: {"changes": [{"campaign_id": 1}, {"campaign_id": 2}, {"campaign_id": 1}]})
    sent = {1: {"updated": 2, "failed": []},
            2: {"updated": 0, "failed": [{"creative_id": 7, "error": "отказ"}, {"creative_id": 8, "error": "отказ"}]}}
    monkeypatch.setattr(volumes_now, "push_limits", lambda db, camp: sent[camp.id])

    out = TB._push_to_campaigns(_Db(camps))

    assert out["campaigns_updated"] is True
    assert out["limits_updated"] == 2
    assert out["limits_failed"] == 2


def test_nothing_moved_sends_nothing(monkeypatch):
    monkeypatch.setattr(build, "refresh_weights", lambda db: {"changes": []})

    def boom(db, camp):
        raise AssertionError("в DSP незачем идти — ничего не сдвинулось")
    monkeypatch.setattr(volumes_now, "push_limits", boom)

    out = TB._push_to_campaigns(_Db([]))
    assert out == {"campaigns_updated": True, "limits_updated": 0, "limits_failed": 0}


def test_recount_failure_says_so(monkeypatch):
    def boom(db):
        raise RuntimeError("сбой")
    monkeypatch.setattr(build, "refresh_weights", boom)
    out = TB._push_to_campaigns(_Db([]))
    assert out["campaigns_updated"] is False
