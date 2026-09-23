# -*- coding: utf-8 -*-
"""Прибор: день входа сделки в стадию — московский.

`sales_deal_stage_history.at` — `timestamptz`, база в UTC. Вход в стадию в 01:30 по
Москве — это 22:30 предыдущих суток по Гринвичу. `.date()` отдавал гринвичский день, а
«сегодня» с 23.09.2026 московское: срок в стадии считался на сутки больше, и просрочка
наступала на день раньше. Ошибка жила три часа в сутки и выглядела правдоподобно.
"""
from datetime import datetime, date, timezone

from app import timez


def test_msk_date_of_an_aware_night_moment():
    # 22:30 UTC 13.09 = 01:30 МСК 14.09
    assert timez.msk_date(datetime(2026, 9, 13, 22, 30, tzinfo=timezone.utc)) == date(2026, 9, 14)


def test_msk_date_of_a_naive_utc_moment():
    assert timez.msk_date(datetime(2026, 9, 13, 22, 30)) == date(2026, 9, 14)


def test_msk_date_keeps_dates_and_none():
    assert timez.msk_date(date(2026, 9, 14)) == date(2026, 9, 14)
    assert timez.msk_date(None) is None


def test_stage_since_reads_the_moscow_day():
    """Сама функция очереди — на живой записи истории, с откатом."""
    from app.database import SessionLocal
    from app.sales.models import SalesDeal, SalesDealStageHistory
    from app.sales.urgency_db import stage_since

    db = SessionLocal()
    db.commit = db.flush
    try:
        deal = db.query(SalesDeal).filter(SalesDeal.our_stage_id.isnot(None)).first()
        if deal is None:
            import pytest
            pytest.skip("нужна сделка со стадией")
        db.add(SalesDealStageHistory(deal_id=deal.id, to_stage_id=deal.our_stage_id,
                                     at=datetime(2099, 9, 13, 22, 30, tzinfo=timezone.utc)))
        db.flush()
        got = stage_since(db, [deal.id])[(deal.id, deal.our_stage_id)]
        assert got == date(2099, 9, 14), got
    finally:
        db.rollback()
        db.close()
