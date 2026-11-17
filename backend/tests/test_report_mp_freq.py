# -*- coding: utf-8 -*-
"""Частота из медиаплана — потолок в отчёте клиенту (17.11.2026, жалоба аккаунта по QZ9VNS: в МП «до 3х», а по неделям 4,4 —
частота дня шла из настроек SIMB ID, база 4 ± 30 %, и МП не смотрела). Числа дня считаются один раз и лежат
(владелец: «посчитались и лежат»): выгрузка их только читает.

Поломки, которые ловит набор:
- новый день фиксируется от базы настроек при заполненной частоте МП;
- худший день модели (поправка +30 %, повторы 16 %, пересечение 8 %) даёт неделю выше частоты МП;
- охват недели меньше «показы ÷ частота МП» — частота в отчёте выше заложенной в медиаплане;
- зафиксированный день пересчитывается: после смены частоты МП или настроек числа другие;
- без частоты в МП что-то меняется (должно остаться как было)."""
import pytest

from app.ad import report_coef as RC

SETTINGS = {"freq_base": 4.0, "freq_dev_pct": 30.0, "ctr_base": 0.8, "ctr_dev_pct": 40.0,
            "repeat_min": 8, "repeat_max": 16, "overlap_min": 3, "overlap_max": 8}


def test_day_base_is_share_of_mp_frequency():
    assert RC.day_base(SETTINGS, 3) == pytest.approx(1.65)      # 3 × 0,55
    assert RC.day_base(SETTINGS, None) == 4.0                  # нет частоты в МП — база настроек
    assert RC.day_base(SETTINGS, 0) == 4.0


def test_worst_day_stays_under_mp_frequency():
    worst = {"freq": RC.day_base(SETTINGS, 3) * 1.3, "ctr_pct": 1.0, "repeat_pct": 16, "overlap_pct": 8}
    d = RC.derive(100000, worst)
    assert 100000 / d["reach"] < 3                           # ≈ 2,78


def test_week_reach_never_below_shows_over_mp_frequency():
    assert RC.week_reach(20000, 90000, 3) == 30000           # модель дала частоту 4,5 — поднимаем охват до 90 000 ÷ 3
    assert RC.week_reach(40000, 90000, 3) == 40000           # частота 2,25 — не трогаем
    assert RC.week_reach(20000, 90000, None) == 20000


@pytest.fixture
def db_cr():
    from datetime import date

    from sqlalchemy import text

    import app.model_registry  # noqa: F401
    from app.database import SessionLocal
    db = SessionLocal()
    cid = db.execute(text("SELECT id FROM ad_campaign_creative ORDER BY id DESC LIMIT 1")).scalar()
    if cid is None:
        db.close()
        pytest.skip("на стенде нет креативов РК")
    day = date(2031, 1, 7)                                   # день, которого у креатива заведомо нет
    try:
        yield db, cid, day
    finally:
        db.rollback()
        db.close()


def test_new_day_is_fixed_from_mp_frequency_and_then_lies_still(db_cr, monkeypatch):
    db, cid, day = db_cr
    monkeypatch.setattr(db, "commit", db.flush)             # не писать в стенд: фиксация видна в той же транзакции
    got = RC.ensure(db, [(cid, day)], SETTINGS, mp_freq=3)[(cid, day)]
    assert 1.65 * 0.7 - 0.01 <= got["freq"] <= 1.65 * 1.3 + 0.01
    again = RC.ensure(db, [(cid, day)], {**SETTINGS, "freq_base": 9.0}, mp_freq=5)[(cid, day)]
    assert again == got                                      # МП и настройки поменялись — лежащий день тот же
