# -*- coding: utf-8 -*-
"""Клик по дню полосы «События» находит каждое событие этого дня (прод, 29.09.2026)."""
from datetime import date
from types import SimpleNamespace

from app.routers.account_dashboard import deal_events


def test_docs_deadline_day_is_found_by_queue_filter():
    d = SimpleNamespace(period_from=date(2026, 9, 1), period_to=date(2026, 9, 27))
    assert ("docs", date(2026, 10, 2)) in deal_events(d)
    assert any(w == date(2026, 10, 2) for _, w in deal_events(d))


def test_empty_dates_give_no_events():
    assert deal_events(SimpleNamespace(period_from=None, period_to=None)) == []
