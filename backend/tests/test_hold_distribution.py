"""Удержание долей первые 5 дней РК (владелец 27.09.2026).

  · до старта РК и первые 5 дней флайта объём РК делят по индексам ВСЕ площадки в
    работе — от «ждёт сборки» до «запущен» и «пауза»; выпадает только «завершена».
    Трафик видит объём каждой площадки до запуска, и креативы уезжают в DSP с лимитом;
  · с 6-го дня — перерасчёт по факту запущенного: делят только «запущен» и «пауза».

То же для креативов внутри площадки: в удержание делят все, кроме отклонённого.
"""
from datetime import date, timedelta

from app.ad.flight import HOLD_DAYS, distribute, flight_of, holds, split_evenly

WAIT, READY, ON, PAUSE, OFF = "ждёт сборки", "ждёт запуска", "запущен", "пауза", "завершена"
START = date(2026, 10, 1)
END = date(2026, 10, 31)


def _rows(out):
    return {r["id"]: r for r in out["rows"]}


def _fl(day_no):
    """Флайт на `day_no`-й день РК (1 — день старта, 0 — накануне)."""
    return flight_of(START, END, START + timedelta(days=day_no - 1))


PLACES = [
    {"id": 1, "status": ON, "weight": 1},
    {"id": 2, "status": READY, "weight": 1},
    {"id": 3, "status": WAIT, "weight": 2},
    {"id": 4, "status": OFF, "weight": 5},
]


def test_hold_window_is_five_days():
    assert HOLD_DAYS == 5
    assert holds(_fl(0)) and holds(_fl(1)) and holds(_fl(5))
    assert not holds(_fl(6))
    assert holds(None), "без дат — предварительное распределение"


def test_before_start_every_placement_in_work_gets_its_share():
    r = _rows(distribute(4000, None, _fl(0), PLACES))
    assert (r[1]["plan_show"], r[2]["plan_show"], r[3]["plan_show"]) == (1000, 1000, 2000)
    assert r[4]["plan_show"] is None, "«завершена» не держит долю никогда"


def test_first_five_days_the_waiting_ones_hold_their_share():
    r = _rows(distribute(4000, None, _fl(5), PLACES))
    assert r[2]["plan_show"] == 1000 and r[3]["plan_show"] == 2000


def test_from_day_six_only_the_launched_share():
    r = _rows(distribute(4000, None, _fl(6), PLACES))
    assert r[1]["plan_show"] == 4000
    assert r[2]["plan_show"] is None and r[3]["plan_show"] is None


def test_pause_keeps_its_share_after_the_hold():
    r = _rows(distribute(4000, None, _fl(10), [
        {"id": 1, "status": ON, "weight": 1}, {"id": 2, "status": PAUSE, "weight": 1}]))
    assert r[1]["plan_show"] == 2000 and r[2]["plan_show"] == 2000


CREATIVES = [
    {"id": 1, "creative_no": 1, "status": "согласован"},
    {"id": 2, "creative_no": 2, "status": "у площадки"},
    {"id": 3, "creative_no": 3, "status": "отклонён"},
    {"id": 4, "creative_no": 4, "status": ON},
]


def test_creatives_in_hold_split_among_all_but_rejected():
    plans = {c["id"]: c["plan_show"] for c in split_evenly(900, CREATIVES, hold=True)}
    assert plans == {1: 300, 2: 300, 3: None, 4: 300}


def test_creatives_after_hold_split_among_ready_to_run():
    """После удержания делят согласованный, запущенный и на паузе: «запущен» у креатива
    ставится только руками, согласованный креатив запущенной площадки уже крутится."""
    plans = {c["id"]: c["plan_show"] for c in split_evenly(900, CREATIVES, hold=False)}
    assert plans == {1: 450, 2: None, 3: None, 4: 450}


def test_every_consumer_passes_the_flight():
    """Удержание решается по дню РК — вызов без флайта молча считал бы «до старта»."""
    import inspect
    from app.ad import build
    src = inspect.getsource(build.recompute_shares)
    assert "flight_of(" in src


# ── индекс из балансировщика сразу в РК (владелец 27.09.2026) ───────────────────

def _camp_with_placement(db, status="запущена"):
    import pytest
    from sqlalchemy import text
    from app.ad.models import AdCampaign, AdCampaignPlacement
    deal_id = db.execute(text(
        "SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
        "WHERE c.id IS NULL ORDER BY d.id LIMIT 1")).scalar()
    pub = db.execute(text("SELECT id FROM sales_publishers WHERE status <> 'АРХИВ' "
                          "ORDER BY id LIMIT 1")).scalar()
    if not (deal_id and pub):
        pytest.skip("нет свободной сделки или площадки")
    camp = AdCampaign(deal_id=deal_id, status=status, plan_show=1000,
                      date_start=date.today(), date_end=date.today() + timedelta(days=20))
    db.add(camp)
    db.flush()
    pl = AdCampaignPlacement(campaign_id=camp.id, publisher_id=pub, weight=1,
                             status="ждёт запуска")
    db.add(pl)
    db.commit()
    return camp, pl, pub


def test_balancer_index_reaches_open_campaigns_at_once(monkeypatch):
    from sqlalchemy import text
    from app.ad import build
    from app.database import SessionLocal
    db = SessionLocal()
    monkeypatch.setattr(build, "deal_plan", lambda db_, d: {"surfaces": ["web"], "services": []})
    monkeypatch.setattr(build, "publisher_weights", lambda db_, surf: {pub: 7.0})
    camp, pl, pub = _camp_with_placement(db)
    try:
        res = build.refresh_weights(db, campaign_ids=[camp.id])
        db.refresh(pl)
        assert pl.weight == 7.0, "индекс балансировщика не дошёл до РК"
        assert pl.plan_show == 1000, "объём не пересчитан после смены веса"
        assert res["campaigns"] >= 1
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()


def test_finished_campaigns_are_left_alone(monkeypatch):
    from sqlalchemy import text
    from app.ad import build
    from app.database import SessionLocal
    db = SessionLocal()
    monkeypatch.setattr(build, "deal_plan", lambda db_, d: {"surfaces": ["web"], "services": []})
    monkeypatch.setattr(build, "publisher_weights", lambda db_, surf: {pub: 7.0})
    camp, pl, pub = _camp_with_placement(db, status="окончена")
    try:
        build.refresh_weights(db, campaign_ids=[camp.id])
        db.refresh(pl)
        assert pl.weight == 1, "завершённую РК перекроили задним числом"
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()


def test_balancer_endpoints_push_the_index_into_campaigns():
    import inspect
    from app.routers import traffic_balancer as tb
    assert "refresh_weights(" in inspect.getsource(tb._push_to_campaigns)
    for fn in (tb.balancer_save_row, tb.balancer_recalc, tb.balancer_import):
        src = inspect.getsource(fn)
        assert "_push_to_campaigns(" in src, fn.__name__
        assert src.index("log_action(") < src.index("_push_to_campaigns("),             f"{fn.__name__}: журнал после пересчёта — сбой пересчёта потеряет запись"


def test_push_failure_does_not_undo_the_saved_index(monkeypatch):
    """Индекс уже сохранён; сбой пересчёта РК не превращается в 500 «ничего не вышло»."""
    from app.ad import build
    from app.routers import traffic_balancer as tb

    class Db:
        rolled = False

        def rollback(self):
            self.rolled = True

    def boom(db):
        raise RuntimeError("упало посередине")
    monkeypatch.setattr(build, "refresh_weights", boom)
    db = Db()
    assert tb._push_to_campaigns(db) is False
    assert db.rolled


def test_refresh_keeps_weights_when_deal_has_no_plan(monkeypatch):
    """Нет годного медиаплана — поверхностей не знаем; веса не обнуляем."""
    from sqlalchemy import text
    from app.ad import build
    from app.database import SessionLocal
    db = SessionLocal()
    monkeypatch.setattr(build, "deal_plan", lambda db_, d: {"surfaces": [], "services": []})
    monkeypatch.setattr(build, "publisher_weights", lambda db_, surf: {})
    camp, pl, pub = _camp_with_placement(db)
    try:
        build.refresh_weights(db, campaign_ids=[camp.id])
        db.refresh(pl)
        assert pl.weight == 1, "веса обнулены из-за отсутствия медиаплана"
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()
