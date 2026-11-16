# -*- coding: utf-8 -*-
"""Коэффициенты SIMB ID для отчёта клиенту (владелец 05.10.2026): на пару «площадка ×
креатив» за день один раз выбирается частота и CTR в пределах базы ± поправки, значение
фиксируется; уники и клики-модель считаются от РЕАЛЬНЫХ показов."""
from datetime import date

import pytest
from sqlalchemy import text

from app.ad import report_coef as RC
from app.database import SessionLocal

SET = {"freq_base": 4.0, "freq_dev_pct": 10, "ctr_base": 0.5, "ctr_dev_pct": 20}
DAY = date(2001, 2, 3)


@pytest.fixture
def db_cr():
    db = SessionLocal()
    cid = db.execute(text("SELECT id FROM ad_campaign_creative ORDER BY id LIMIT 1")).scalar()
    if cid is None:
        db.close()
        pytest.skip("на стенде нет креативов")
    yield db, cid
    db.execute(text("DELETE FROM report_daily_coef WHERE date = :d"), {"d": DAY})
    db.commit()
    db.close()


def test_value_is_in_range_and_fixed(db_cr):
    db, cid = db_cr
    got = RC.ensure(db, [(cid, DAY)], SET)[(cid, DAY)]
    assert 3.6 <= got["freq"] <= 4.4 and 0.4 <= got["ctr_pct"] <= 0.6
    # повторный вызов — то же значение, даже при других настройках
    again = RC.ensure(db, [(cid, DAY)], {**SET, "freq_base": 9.0, "ctr_base": 3.0})[(cid, DAY)]
    assert again == got


def test_zero_correction_gives_base(db_cr):
    db, cid = db_cr
    flat = {"freq_base": 3.7, "freq_dev_pct": 0, "ctr_base": 0.25, "ctr_dev_pct": 0}
    got = RC.ensure(db, [(cid, DAY)], flat)[(cid, DAY)]
    assert (got["freq"], got["ctr_pct"]) == (3.7, 0.25)


def test_reach_numbers_in_range_and_fixed(db_cr):
    """Расчётный охват (16.11.2026): повторы и пересечение — из диапазонов настроек, фиксируются разово. Уронит: числа вне
    диапазона / перевыбор при повторной выгрузке или после правки настроек."""
    db, cid = db_cr
    rng = {**SET, "repeat_min": 8, "repeat_max": 16, "overlap_min": 3, "overlap_max": 8}
    got = RC.ensure(db, [(cid, DAY)], rng)[(cid, DAY)]
    assert 8 <= got["repeat_pct"] <= 16 and 3 <= got["overlap_pct"] <= 8
    again = RC.ensure(db, [(cid, DAY)], {**rng, "repeat_min": 50, "repeat_max": 60})[(cid, DAY)]
    assert again == got


def test_derived_from_real_shows():
    got = RC.derive(1000, {"freq": 4.0, "ctr_pct": 0.5})
    assert (got["uniques"], got["clicks"], got["reach"]) == (250, 5, 250), "без чисел охвата — охват = уники"
    assert RC.derive(0, {"freq": 4.0, "ctr_pct": 0.5}) == {"uniques": 0, "clicks": 0, "reach": 0}
