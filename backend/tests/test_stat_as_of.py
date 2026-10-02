# -*- coding: utf-8 -*-
"""Дата среза статистики (владелец 02.10.2026).

Факт DSP приходит за вчера (крон ночью), а план считался на сегодня — РК всегда на день
«отставала». Weborama снимается утром и приносит ещё и неполный текущий день: сверка
«DSP за сутки против WR за полтора дня» читалась как задвоение. Правило одно: всё —
план, темп, стена дней, сверка с WR — считается по последнему дню, за который пришёл
факт DSP, и только по площадкам, у которых этот факт есть.
"""
import inspect
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import text

import app.main  # noqa: F401
from app.ad import stat_sources as ss
from tests.test_mismatch_level import _call_stat, _stat_camp


class _Db:
    def __init__(self, *answers):
        self.answers = list(answers)

    def execute(self, *a, **k):
        v = self.answers.pop(0)
        return SimpleNamespace(scalar=lambda: v)


def test_as_of_is_last_combat_fact_day():
    t = date(2026, 10, 2)
    assert ss.fact_as_of(_Db(date(2026, 10, 1)), t) == date(2026, 10, 1)


def test_as_of_without_combat_falls_to_own_then_yesterday():
    t = date(2026, 10, 2)
    assert ss.fact_as_of(_Db(None, date(2026, 9, 30)), t) == date(2026, 9, 30)
    assert ss.fact_as_of(_Db(None, None), t) == date(2026, 10, 1)


def test_comparable_skips_placements_outside_our_fact():
    """Площадка вне DSP (прямой тег у аптеки) мерится только Weborama — сверять не с чем."""
    assert ss.comparable(1000, {1: 1000, 2: 0}, {"shows": 6000, "by_placement": {1: 1100, 2: 5000}}) \
        == (1000, 1100, 1)


def test_wr_after_as_of_is_not_compared(monkeypatch):
    from app.database import SessionLocal
    from app.routers import traffic_dashboard as td
    y = date.today() - timedelta(days=1)
    monkeypatch.setattr(td, "fact_as_of", lambda db_, t=None: y)   # ДО создания РК: упади
    db = SessionLocal()                                             # здесь — РК бы осталась
    camp, pls, deal_id, today = _stat_camp(db)
    try:
        ins = ("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, "
               "source) VALUES (:c, :p, :d, :s, 1, :src)")
        db.execute(text(ins), {"c": camp.id, "p": pls[0].id, "d": y, "s": 1000, "src": "demo"})
        db.execute(text(ins), {"c": camp.id, "p": pls[0].id, "d": y, "s": 1050, "src": "weborama"})
        db.execute(text(ins), {"c": camp.id, "p": pls[0].id, "d": today, "s": 700, "src": "weborama"})
        db.commit()
        out = _call_stat(db, camp, deal_id)
        assert out["totals"]["period"]["wr"]["shows"] == 1050, "WR за неполный день попал в сверку"
        assert out["totals"]["as_of"] == y
        assert out["totals"]["today"]["shows"] == 1000, "«день» — последний отчитанный"
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()


def test_every_plan_calculation_uses_as_of():
    from app.routers import sales_dashboard as sd, traffic_dashboard as td
    from app.sales import deal_delivery
    for fn in (td.dashboard, td.campaign, td.campaign_stat, sd.deal_campaign,
               sd.deal_campaign_stat, deal_delivery.delivery_by_deal):
        assert "fact_as_of(" in inspect.getsource(fn), fn.__name__


def test_frozen_as_of_is_flagged():
    """Съём DSP встал — срез застыл; без флага все РК выглядели бы «в графике»."""
    t = date(2026, 10, 5)
    assert not ss.is_stale(date(2026, 10, 4), t)
    assert ss.is_stale(date(2026, 10, 2), t)


def test_wr_outside_our_fact_is_reported_separately():
    assert ss.wr_outside({1: 1000, 2: 0}, {"by_placement": {1: 1100, 2: 5000, 3: 70}}) == 5070
    assert ss.wr_outside({1: 1000}, None) == 0


def test_campaign_started_today_is_not_awaiting_start():
    """Срез — вчера, старт — сегодня: РК уже крутит, «стартует через 1 день» — ложь."""
    from app.ad.flight import progress
    t = date(2026, 10, 2)
    out = progress(1000, None, t, t + timedelta(days=9), t - timedelta(days=1), now=t)
    assert out["days_to_start"] is None
    later = progress(1000, None, t + timedelta(days=3), t + timedelta(days=9),
                     t - timedelta(days=1), now=t)
    assert later["days_to_start"] == 3
