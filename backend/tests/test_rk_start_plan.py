# -*- coding: utf-8 -*-
"""Запуск РК (владелец 01.10.2026, первый боевой запуск 54ZYCH): массовый старт поднимает
«ждёт запуска» по тому же правилу, что кнопка площадки; сделка уходит «В размещении»."""
from types import SimpleNamespace as NS

from app.routers import traffic_dashboard as td


def _c():
    return NS(deal_id=1)


def _p():
    return NS(publisher_id=2)


def test_ready_placement_is_raisable():
    assert td.PLACEMENT_READY in td.START_RAISABLE


def test_start_block_needs_agreed_creative():
    assert td.start_block(None, _c(), _p(), [{"status": "у площадки"}], "dsp") == \
        "нет согласованного креатива"


def test_start_block_needs_dsp_upload_for_our_dsp():
    agreed = [{"status": "согласован", "ms_creative_xxhash": None}]
    assert "В DSP" in td.start_block(None, _c(), _p(), agreed, "dsp")
    assert td.start_block(None, _c(), _p(), agreed, "external") is None
    up = [{"status": "согласован", "ms_creative_xxhash": "AB"}]
    assert td.start_block(None, _c(), _p(), up, "dsp") is None


def test_advance_deal_never_goes_back(monkeypatch):
    from app.sales import catalog as cm
    st = [NS(id=1, name="Готовятся к старту"), NS(id=2, name="В размещении"),
          NS(id=3, name="Итоговая сверка")]
    monkeypatch.setattr(cm, "Catalog", lambda db: NS(
        stages=st, by_id={s.id: s for s in st}, is_before=lambda a, b: a < b))
    deal = NS(our_stage_id=3)
    r = td.advance_deal(None, deal, "В размещении", NS(id=1), "тест")
    assert r == {"moved": False, "stage": "Итоговая сверка", "refused": None}


def test_advance_deal_moves_forward(monkeypatch):
    from app.sales import catalog as cm
    from app.sales import stage_move
    st = [NS(id=1, name="Готовятся к старту"), NS(id=2, name="В размещении")]
    monkeypatch.setattr(cm, "Catalog", lambda db: NS(
        stages=st, by_id={s.id: s for s in st}, is_before=lambda a, b: a < b))
    monkeypatch.setattr(stage_move, "plan_move", lambda *a: NS())
    monkeypatch.setattr(stage_move, "may_move", lambda plan: True)
    moved = []
    monkeypatch.setattr(stage_move, "apply_move", lambda db, d, t, u, **k: moved.append(t.name))
    r = td.advance_deal(None, NS(our_stage_id=1), "В размещении", NS(id=1), "тест")
    assert r["moved"] and moved == ["В размещении"]


def test_advance_deal_reports_refusal(monkeypatch):
    from app.sales import catalog as cm
    from app.sales import stage_move
    st = [NS(id=1, name="Готовятся к старту"), NS(id=2, name="В размещении")]
    monkeypatch.setattr(cm, "Catalog", lambda db: NS(
        stages=st, by_id={s.id: s for s in st}, is_before=lambda a, b: a < b))
    monkeypatch.setattr(stage_move, "plan_move", lambda *a: NS(not_applicable=False, allowed=False))
    monkeypatch.setattr(stage_move, "may_move", lambda plan: False)
    monkeypatch.setattr(stage_move, "refusal_text", lambda plan: "нет ЕРИД")
    r = td.advance_deal(None, NS(our_stage_id=1), "В размещении", NS(id=1), "тест")
    assert r == {"moved": False, "stage": "Готовятся к старту", "refused": "нет ЕРИД"}


def test_one_pair_ready_is_the_only_blocking_check_of_running_stage():
    """Вход в «В размещении» — по одной собранной площадке (миграция 2026-10-01)."""
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT c.check_key FROM sales_stage_checks c JOIN sales_stages s ON s.id = c.stage_id "
            "WHERE s.name = 'В размещении' AND c.is_blocking")).scalars().all()
        assert rows == ["one_pair_ready"], rows
    finally:
        db.close()


def test_one_pair_ready_registered():
    from app.sales import stage_checks as sc
    assert "one_pair_ready" in sc.REGISTRY and sc.REGISTRY["one_pair_ready"].where


def test_plan_reaches_end_of_flight_before_first_fact():
    """Первый день запуска, показов ещё нет (факт None): план рисуется до конца флайта."""
    from datetime import date
    from app.ad.flight import daily_buckets, flight_of
    fl = flight_of(date(2026, 10, 1), date(2026, 10, 31), today=date(2026, 10, 1))
    r = daily_buckets(310000, None, fl, {}, grain="day", today=date(2026, 10, 1))
    assert len(r["buckets"]) == 31 and all(b["plan"] > 0 for b in r["buckets"])
    w = daily_buckets(310000, None, fl, {}, grain="week", today=date(2026, 10, 1))
    assert len(w["buckets"]) == 5 and w["buckets"][1]["plan"] > 7 * 10000


def test_paused_before_any_show_returns_pair_from_placed():
    """EDUYRT 01.10.2026: отметили запущенной и сразу сняли — пара не остаётся «в размещении».
    С показами — остаётся: размещение состоялось."""
    from sqlalchemy import text
    from app.ad import build
    from app.ad.models import AdCampaignPlacement
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT p.id, t.id AS tid FROM ad_campaign_placement p
              JOIN ad_campaign a ON a.id = p.campaign_id
              JOIN launch_prep_target t ON t.deal_id = a.deal_id AND t.publisher_id = p.publisher_id
             WHERE t.archived_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM ad_campaign_stat s WHERE s.placement_id = p.id AND s.shows > 0)
             LIMIT 1""")).first()
        if not row:
            import pytest
            pytest.skip("нет площадки с получателем без показов")
        pl = db.get(AdCampaignPlacement, row.id)
        db.execute(text("UPDATE launch_prep_target SET state = 'в размещении' WHERE id = :t"), {"t": row.tid})
        assert build.unmark_target_placed(db, pl) >= 1
        assert db.execute(text("SELECT state FROM launch_prep_target WHERE id = :t"),
                          {"t": row.tid}).scalar() == build.TARGET_ERID
        db.execute(text("UPDATE launch_prep_target SET state = 'в размещении' WHERE id = :t"), {"t": row.tid})
        db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
                        "VALUES (:c, :p, current_date, 10, 0, 'demo')"), {"c": pl.campaign_id, "p": pl.id})
        assert build.unmark_target_placed(db, pl) == 0, "были показы — размещение состоялось"
    finally:
        db.rollback()
        db.close()
