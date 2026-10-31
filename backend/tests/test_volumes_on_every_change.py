# -*- coding: utf-8 -*-
"""Изменение внутри РК — объёмы и лимиты в DSP сразу, а не ночью (владелец 31.10.2026: «делай»).

Правило одно: событие, меняющее раскладку РК, заканчивается пересчётом и отправкой в DSP лимитов тех креативов,
у которых план сдвинулся (`volumes_now.push_limits` → `dsp.limits.sync_limits`, мелочь < 1 % / 100 не шлёт).
Раньше так делали только запуск площадки и «ок» площадки; остальные события пересобирали РК, а лимиты в DSP
оставались вчерашними до ночного прогона. Сбой отправки действие не роняет — ночь остаётся страховкой.

Что ночью и только ночью (по делу): переключение на 6-й день, «план не ниже факта» по свежему факту, закрытие
истёкшего «Темпа размещения».
"""
from types import SimpleNamespace

import pytest

from app.ad import build, volumes_now


class _Q:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a, **k):
        return self

    def get(self, i):
        return next((r for r in self.rows if r.id == i), None)

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *a):
        return _Q(self.rows)

    def commit(self):
        pass

    def rollback(self):
        pass

    def flush(self):
        pass


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(volumes_now, "push_limits",
                        lambda db, camp, client=None: out.append(camp.id) or {"campaign_id": camp.id})
    return out


def test_event_resync_sends_limits_to_dsp(monkeypatch, sent):
    """Пересборка РК по событию (вердикт, ЕРИД, отправка, отзыв, объём креатива) — лимиты в DSP сразу."""
    monkeypatch.setattr(build, "sync_deal", lambda db, deal_id, **k: {"created": 0})
    build.sync_deal_quietly(_Db([SimpleNamespace(id=5, deal_id=1, ms_campaign_xxhash="X")]), 1)
    assert sent == [5]


def test_failed_resync_sends_nothing_and_does_not_raise(monkeypatch, sent):
    def boom(db, deal_id, **k):
        raise RuntimeError("сборка упала")
    monkeypatch.setattr(build, "sync_deal", boom)
    build.sync_deal_quietly(_Db([SimpleNamespace(id=5, deal_id=1, ms_campaign_xxhash="X")]), 1)
    assert sent == [], "по недособранной РК лимиты не шлём — догонит ночь"


def test_balancer_sends_limits_only_where_plans_moved(monkeypatch, sent):
    """Правка индекса трогает все РК площадки — в DSP идут только те, где план площадки сдвинулся."""
    from app.routers import traffic_balancer as tb
    monkeypatch.setattr(build, "refresh_weights", lambda db, **k: {"changes": [
        {"campaign_id": 5, "placement_id": 1, "plan_before": 100, "plan_after": 120},
        {"campaign_id": 7, "placement_id": 2, "plan_before": 50, "plan_after": 40}]})
    camps = [SimpleNamespace(id=i, ms_campaign_xxhash="X") for i in (5, 7)]
    asked = []

    class _BDb(_Db):
        def query(self, *a):
            return SimpleNamespace(filter=lambda cond: asked.append(cond) or _Q(camps))

    assert tb._push_to_campaigns(_BDb(camps))["campaigns_updated"] is True
    assert sorted(sent) == [5, 7]


def test_balancer_without_moved_plans_sends_nothing(monkeypatch, sent):
    from app.routers import traffic_balancer as tb
    monkeypatch.setattr(build, "refresh_weights", lambda db, **k: {"changes": []})
    assert tb._push_to_campaigns(_Db([SimpleNamespace(id=5, ms_campaign_xxhash="X")]))["campaigns_updated"] is True
    assert sent == []


def test_rejecting_a_creative_sends_the_siblings_limits(monkeypatch, sent):
    """Отклонение креатива отдаёт его объём соседям по площадке — их лимиты в DSP тоже сразу, а не ночью."""
    from app.routers import traffic_dashboard as td
    cr = SimpleNamespace(id=3, campaign_id=5, status="согласован", ms_title="X-1-cr1")
    camp = SimpleNamespace(id=5, ms_campaign_xxhash="X")
    monkeypatch.setattr(td, "_campaign_in_scope", lambda db, cid, u: (camp, None))
    monkeypatch.setattr(td, "_lock_shares", lambda db, cid: None)
    monkeypatch.setattr(td.build, "recompute_shares", lambda db, cid: [])
    monkeypatch.setattr(td, "_creative_to_dsp", lambda db, c, cr, old: None)
    monkeypatch.setattr(td, "log_action", lambda *a, **k: None)
    td.set_creative_status(3, td.StatusIn(status="отклонён"), _Db([cr]), SimpleNamespace(id=1))
    assert sent == [5]


def test_pausing_a_creative_does_not_touch_other_limits(monkeypatch, sent):
    """Пауза креатива долю держит — раскладка не меняется, лишний проход по DSP не нужен."""
    from app.routers import traffic_dashboard as td
    cr = SimpleNamespace(id=3, campaign_id=5, status="запущен", ms_title="X-1-cr1")
    camp = SimpleNamespace(id=5, ms_campaign_xxhash="X")
    monkeypatch.setattr(td, "_campaign_in_scope", lambda db, cid, u: (camp, None))
    monkeypatch.setattr(td, "_lock_shares", lambda db, cid: None)
    monkeypatch.setattr(td, "_creative_to_dsp", lambda db, c, cr, old: None)
    monkeypatch.setattr(td, "log_action", lambda *a, **k: None)
    td.set_creative_status(3, td.StatusIn(status="пауза"), _Db([cr]), SimpleNamespace(id=1))
    assert sent == []
