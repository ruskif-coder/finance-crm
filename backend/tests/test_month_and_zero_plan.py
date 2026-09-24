# -*- coding: utf-8 -*-
"""Две мелочи этапа 7 (аудит 23.09.2026, 3.L4 и 3.L5).

3.L4. Фильтр периода «2026-13» проходил проверку формата (четыре цифры, дефис, две) и
падал уже в расчёте дат — 500 вместо понятного отказа.

3.L5. Сделка из медиаплана со 100 % скидкой не создавалась: «строк размещения нет»
определялось по нулевой сумме плана. Решение владельца 24.09.2026: такая сделка —
законная, их потом собирают в мастер-сделку. Проверяются сами строки, а не сумма.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import media_plans as mp
from app.routers import sales_dashboard as sd


@pytest.mark.parametrize("bad", ["2026-13", "2026-00"])
def test_a_month_out_of_range_is_a_clear_refusal(bad):
    with pytest.raises(HTTPException) as e:
        sd._month_bounds(bad, False)
    assert e.value.status_code == 400


def test_a_real_month_still_works():
    # Граница конца — ИСКЛЮЧАЮЩАЯ: первое число следующего месяца.
    assert sd._month_bounds("2026-02", True) == "2026-03-01"
    assert sd._month_bounds("2026-12", True) == "2027-01-01"


def test_a_zero_sum_plan_with_rows_gets_a_deal(monkeypatch):
    plan = SimpleNamespace(id=1, deal_id=None, period="2026-10", advertiser_id=3,
                           agency_id=None, amount_net=0)
    row = SimpleNamespace(position="еФарм", sort_order=0)

    class _Q:
        def __init__(self, item):
            self.item = item

        def filter(self, *a):
            return self

        def order_by(self, *a):
            return self

        def first(self):
            return self.item

        def count(self):
            return 1 if self.item else 0

    class _Db:
        def query(self, model):
            return _Q(plan if model is mp.SalesMediaPlan else row)

    monkeypatch.setattr(mp, "_guard_owned", lambda *a, **kw: None)

    class _Stop(Exception):
        pass

    def stop(*a, **kw):
        raise _Stop()
    # Дальше проверок начинается создание сделки — нам достаточно дойти до него.
    monkeypatch.setattr(mp, "_names", stop)
    with pytest.raises(_Stop):
        mp.create_deal_from_plan(1, mp.CreateDealIn(), _Db(), SimpleNamespace(id=1))


@pytest.mark.parametrize("bad", ["2026-13", "2026-00"])
def test_one_period_rule_for_filter_and_bulk_edit(bad):
    """Массовая правка проверяет период тем же правилом, что фильтр: «2026-13» и там
    давал 500 на `date(2026, 13, 1)` (ревью этапа 7, 24.09.2026)."""
    assert sd._PERIOD_RE.match(bad) is None
    assert sd._PERIOD_RE.match("2026-12")
