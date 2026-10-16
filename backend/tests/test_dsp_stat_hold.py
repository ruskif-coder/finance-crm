# -*- coding: utf-8 -*-
"""Стоп ночного пересчёта при поломке сбора DSP и кнопка «Возобновить» (владелец 16.10.2026).

Сбор упал → пересчёт долей не идёт: иначе он раскладывает объём по нулям (15.10). Снимает стоп
только человек — автоматически по «хорошему» прогону нельзя: один удачный день не значит, что
дыры в данных закрыты."""
import pytest

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.dsp import stat_hold as H


@pytest.fixture
def db():
    s = SessionLocal()
    saved = H.get(s)
    H.clear(s, None)
    s.commit()
    yield s
    s.rollback()
    H.clear(s, None)
    if saved:
        H.engage(s, saved["reason"])
    s.commit()
    s.close()


def test_engage_is_sticky_and_keeps_first_reason(db):
    assert H.get(db) is None
    H.engage(db, "AccessDenied по креативам")
    H.engage(db, "другая причина")
    h = H.get(db)
    assert h["reason"] == "AccessDenied по креативам" and h["since"]


def test_resume_clears(db):
    H.engage(db, "x")
    H.clear(db, None)
    assert H.get(db) is None


def test_daily_shares_skips_while_held(db, monkeypatch):
    from app.ad import daily_shares as DS
    H.engage(db, "сбор упал")
    db.commit()
    called = []
    monkeypatch.setattr("app.ad.build.refresh_weights", lambda *a, **k: called.append(1) or {})
    out = DS.run()
    assert out.get("held") and not called, "пересчёт по нулям при сломанном сборе"


def test_bad_collection_engages_hold(db, monkeypatch):
    from app.dsp import stat_daily as SD
    monkeypatch.setattr(SD, "_emit", lambda *a: None)
    SD.after_planned_run(prev_bad=False, out={"denied": ["A"]}, error=None)
    assert H.get(db) is not None
    H.clear(db, None); db.commit()
    SD.after_planned_run(prev_bad=False, out={}, error=None)
    assert H.get(db) is None, "хороший прогон стоп не ставит"
