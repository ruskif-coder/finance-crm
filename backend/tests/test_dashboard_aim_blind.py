# -*- coding: utf-8 -*-
"""Кнопка «◎ нацелить» (владелец 09.10.2026): активна, когда у комплекта есть НАША веб-площадка
с СОГЛАСОВАННЫМ креативом и ГОТОВЫМ ЕРИД. Правило одно — `aim_gate`: его читают и дашборд
(`aim_off` в строках креативов), и ручка выпуска ссылки (409 с той же причиной)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.dsp import targeting_creative as tc
from app.routers.traffic_dashboard import _creatives_of


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _fake(db, monkeypatch, pairs, sets):
    """Подмена чтения базы: пары (set_id, surface, our_code, agreed) и комплекты."""
    class _R:
        def all(self):
            return pairs

    monkeypatch.setattr(db, "execute", lambda *a, **k: _R())
    monkeypatch.setattr(db, "query", lambda *_a: SimpleNamespace(
        filter=lambda *_b: SimpleNamespace(all=lambda: sets)))


def _set(i, erid="", src="simb", ord_status=None):
    return SimpleNamespace(id=i, no=i, erid=erid, erid_source=src, ord_status=ord_status)


def test_gate_names_the_missing_condition(db, monkeypatch):
    pairs = [(1, "web", False, True),            # чужая DSP
             (2, "web", True, False),            # наша, не согласована
             (3, "web", True, True),             # наша, согласована, маркер готов
             (4, "web", True, True),             # наша, согласована, маркер не выдан
             (5, "web", False, True), (5, "web", True, True),   # смешанный: наша пара согласована
             (6, "app", True, True)]             # приложение — нацеливание не покажет
    sets = [_set(1), _set(2), _set(3, "2SDnjcXXXXX", ord_status="Active"), _set(4),
            _set(5, "2SDnjcYYYYY", ord_status="Registering"), _set(6, "2SDnjcZZZZZ", ord_status="Active")]
    _fake(db, monkeypatch, pairs, sets)
    got = tc.aim_gate(db, [1, 2, 3, 4, 5, 6])
    assert got[1] == tc.BLIND_TEXT
    assert got[2] == tc.NO_AGREED_TEXT
    assert got[3] is None
    assert got[4].startswith("Ждём ЕРИД")
    assert got[5] is None                        # Registering готов (правило ord/readiness)
    assert got[6] == tc.BLIND_TEXT


def test_withdrawn_or_refused_pair_does_not_open_the_button(db, monkeypatch):
    """Согласование отозвано (`agreed` ложно) — кнопка снова заперта, хотя маркер готов."""
    _fake(db, monkeypatch, [(7, "web", True, False)], [_set(7, "2SDnjcXXXXX", ord_status="Active")])
    assert tc.aim_gate(db, [7])[7] == tc.NO_AGREED_TEXT


def test_every_creative_row_carries_the_gate_and_it_matches_the_function(db):
    cid = db.execute(text(
        "SELECT campaign_id FROM ad_campaign_creative c JOIN launch_prep_pair p ON p.id = c.pair_id "
        "GROUP BY campaign_id ORDER BY count(*) DESC LIMIT 1")).scalar()
    if not cid:
        pytest.skip("на стенде нет РК с креативами")
    rows = [r for rs in _creatives_of(db, cid).values() for r in rs]
    assert rows and all("aim_off" in r for r in rows)
    want = tc.aim_gate(db, {r["set_id"] for r in rows if r["set_id"]})
    for r in rows:
        assert r["aim_off"] == want.get(r["set_id"])


def test_endpoint_refuses_with_the_gate_reason(db, monkeypatch):
    from fastapi import HTTPException
    from app.routers import launch_prep as lp
    sid = db.execute(text("SELECT id FROM launch_prep_creative_set LIMIT 1")).scalar()
    if not sid:
        pytest.skip("нет комплектов")
    monkeypatch.setattr(tc, "aim_gate", lambda _db, ids: {ids[0]: tc.NO_AGREED_TEXT})
    user = SimpleNamespace(id=None, role=SimpleNamespace(key="admin"))
    with pytest.raises(HTTPException) as e:
        lp.issue_targeting_link(sid, db=db, current_user=user, first_check=False)
    assert e.value.status_code == 409 and tc.NO_AGREED_TEXT in e.value.detail
