"""Расхождение нашего факта с Weborama — цвет и порог (владелец 27.09.2026).

  · порог — 10 % базово, если в плановых показателях сделки не указано другое число;
  · зелёный — расхождение не больше порога;
  · жёлтый — больше порога, но не больше двух порогов (при 10 % — 10–20 %);
  · красный — больше двух порогов (20 %+);
  · Weborama больше нашего факта — красный отдельно: это проблема съёма статистики
    на нашей стороне («больше нашего не видел никогда»).
"""
from app.ad import stat_sources as ss


def test_threshold_is_ten_by_default_and_taken_from_the_goal():
    assert ss.goal_limit(None) == 10
    assert ss.goal_limit({}) == 10
    assert ss.goal_limit({"weborama": "до 15 %"}) == 15
    assert ss.goal_limit({"weborama": "7,5"}) == 7.5
    assert ss.goal_limit({"weborama": "по факту"}) == 10


def test_colours_by_the_owners_scale():
    assert ss.mismatch_level(None, 10) is None
    assert ss.mismatch_level(4.2, 10)["level"] == "ok"
    assert ss.mismatch_level(10, 10)["level"] == "ok"
    assert ss.mismatch_level(12, 10)["level"] == "warn"
    assert ss.mismatch_level(20, 10)["level"] == "warn"
    assert ss.mismatch_level(20.1, 10)["level"] == "bad"


def test_weborama_above_our_fact_is_our_collection_problem():
    v = ss.mismatch_level(-3.0, 10)
    assert v["level"] == "bad" and v["reason"] == "wr_higher"
    assert "на нашей стороне" in v["hint"]


def test_campaign_stat_puts_weborama_next_to_our_fact(monkeypatch):
    """Итоги под графиком РК: «факт | WR» и расхождение с цветом — на живой базе.

    Дата среза зафиксирована на сегодня: тест про раскладку сверки, а срез проверяет
    `test_stat_as_of` (на боевой копии срез — вчера, и сегодняшний факт отрезался бы)."""
    from datetime import date, timedelta
    from types import SimpleNamespace
    import pytest
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.ad.models import AdCampaign
    from app.routers import traffic_dashboard as td
    monkeypatch.setattr(td, "fact_as_of", lambda db_, t=None: date.today())
    db = SessionLocal()
    deal_id = db.execute(text("SELECT id FROM sales_deals ORDER BY id LIMIT 1")).scalar()
    if not deal_id:
        pytest.skip("нет сделки")
    today = date.today()
    camp = AdCampaign(deal_id=deal_id, status="запущена", plan_show=10000,
                      date_start=today - timedelta(days=5), date_end=today + timedelta(days=5))
    db.add(camp)
    db.commit()
    try:
        for d, own, wr in ((today - timedelta(days=1), 1000, 850), (today, 500, 480)):
            db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, date, shows, clicks, source) "
                            "VALUES (:c, :d, :s, 10, 'demo'), (:c, :d, :w, 5, 'weborama')"),
                       {"c": camp.id, "d": d, "s": own, "w": wr})
        db.commit()
        orig = td._campaign_in_scope
        td._campaign_in_scope = lambda db_, cid, u: (camp, SimpleNamespace(id=deal_id))
        try:
            out = td.campaign_stat(camp.id, db=db, user=SimpleNamespace(id=1))
        finally:
            td._campaign_in_scope = orig
        per, tod = out["totals"]["period"], out["totals"]["today"]
        assert per["shows"] == 1500 and per["wr"]["shows"] == 1330
        assert per["mismatch"]["pct"] == 11.3 and per["mismatch"]["level"] in ("warn", "ok")
        assert tod["wr"]["shows"] == 480 and tod["mismatch"]["pct"] == 4.0
        # Карточка дня «Динамики показов» — WR за этот день рядом с фактом.
        day = next(b for b in out["buckets"] if b["date_from"] == today - timedelta(days=1))
        assert day["wr_shows"] == 850 and day["mismatch"]["pct"] == 15.0
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()


# ── сравниваем сопоставимое (ревью 27.09.2026) ──────────────────────────────────
#
# Карточка сделки сверяла только площадки, которые Weborama мерила (случай 14.09: 77 %
# по всей РК против 10 % по единственной покрытой). Дашборд трафика делил WR по части
# площадок на факт всей РК и вешал ложное «Большое расхождение с WR». Правило одно —
# `stat_sources.comparable`; ручной итог за период (`weborama_manual`) в график по дням
# не идёт: это одно число на весь период, датированное его концом.

def test_comparable_takes_only_measured_placements():
    own, wr, n = ss.comparable(3000, {1: 1000, 2: 2000}, {"shows": 900, "by_placement": {1: 900}})
    assert (own, wr, n) == (1000, 900, 1)


def test_comparable_falls_back_to_the_whole_campaign_without_placements():
    own, wr, n = ss.comparable(3000, {1: 1000, 2: 2000}, {"shows": 2700, "by_placement": {}})
    assert (own, wr, n) == (3000, 2700, 0)
    assert ss.comparable(3000, {}, None) == (3000, None, 0)


def test_every_screen_asks_the_same_comparison():
    import inspect
    from app.routers import sales_dashboard as sd, traffic_dashboard as td
    assert "comparable(" in inspect.getsource(sd.deal_campaign)
    assert "comparable(" in inspect.getsource(td.campaign_stat)
    assert "comparable(" in inspect.getsource(td.dashboard)


def _stat_camp(db):
    from datetime import date, timedelta
    import pytest
    from sqlalchemy import text
    from app.ad.models import AdCampaign, AdCampaignPlacement
    deal_id = db.execute(text(
        "SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
        "WHERE c.id IS NULL ORDER BY d.id LIMIT 1")).scalar()
    pubs = [p for (p,) in db.execute(text(
        "SELECT id FROM sales_publishers ORDER BY id LIMIT 2")).all()]
    if not deal_id or len(pubs) < 2:
        pytest.skip("нет свободной сделки или двух площадок")
    today = date.today()
    camp = AdCampaign(deal_id=deal_id, status="запущена", plan_show=10000,
                      date_start=today - timedelta(days=5), date_end=today + timedelta(days=5))
    db.add(camp)
    db.flush()
    pls = [AdCampaignPlacement(campaign_id=camp.id, publisher_id=p) for p in pubs]
    db.add_all(pls)
    db.commit()
    return camp, pls, deal_id, today


def _call_stat(db, camp, deal_id):
    from types import SimpleNamespace
    from app.routers import traffic_dashboard as td
    orig = td._campaign_in_scope
    td._campaign_in_scope = lambda db_, cid, u: (camp, SimpleNamespace(id=deal_id))
    try:
        return td.campaign_stat(camp.id, db=db, user=SimpleNamespace(id=1))
    finally:
        td._campaign_in_scope = orig


def test_campaign_stat_compares_only_measured_placements(monkeypatch):
    from datetime import date, timedelta
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.routers import traffic_dashboard as td
    # Срез статистики — последний день БОЕВОГО факта на стенде, а стенд — копия прода на день снимка.
    # Без фиксации тест проходил, пока «вчера» совпадало с последним днём факта в копии, и краснел со
    # следующих суток (07.10.2026), хотя код не менялся. Сам срез проверяет `test_stat_as_of`
    # (он ЗОВЁТ общий `_call_stat`, поэтому срез фиксируется здесь, а не в помощнике).
    monkeypatch.setattr(td, "fact_as_of", lambda db_, t=None: date.today())
    db = SessionLocal()
    camp, pls, deal_id, today = _stat_camp(db)
    try:
        y = today - timedelta(days=1)
        for p in pls:
            db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, "
                            "shows, clicks, source) VALUES (:c, :p, :d, 1000, 10, 'demo')"),
                       {"c": camp.id, "p": p.id, "d": y})
        db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, "
                        "shows, clicks, source) VALUES (:c, :p, :d, 900, 5, 'weborama')"),
                   {"c": camp.id, "p": pls[0].id, "d": y})
        db.commit()
        out = _call_stat(db, camp, deal_id)
        per = out["totals"]["period"]
        assert per["shows"] == 2000, "факт РК на экране — весь"
        assert per["mismatch"]["pct"] == 10.0, "сверка по всей РК, а мерили одну площадку"
        day = next(b for b in out["buckets"] if b["date_from"] == y)
        assert day["mismatch"]["pct"] == 10.0
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()


def test_manual_period_total_stays_out_of_the_daily_chart():
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    camp, pls, deal_id, today = _stat_camp(db)
    try:
        db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, date, shows, clicks, "
                        "source) VALUES (:c, :d, 1000, 10, 'demo')"),
                   {"c": camp.id, "d": today})
        db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, date, shows, clicks, "
                        "source) VALUES (:c, :d, 5000, 0, 'weborama_manual')"),
                   {"c": camp.id, "d": today})
        db.commit()
        out = _call_stat(db, camp, deal_id)
        day = next(b for b in out["buckets"] if b["date_from"] == today)
        assert day.get("wr_shows") is None, "итог за период нарисован одним днём"
        assert out["totals"]["today"]["wr"]["shows"] is None
        assert out["totals"]["period"]["wr"]["shows"] == 5000
    finally:
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        db.commit()
        db.close()
