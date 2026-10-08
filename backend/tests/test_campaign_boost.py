# -*- coding: utf-8 -*-
"""«Темп размещения» (08.10.2026): остаток РК временно поднят на X % на N дней.

Что держит тест: границы ввода, множитель только на запущенные площадки без заданного объёма и
не выбывшие, ровно X % от их остатка, возврат к исходному плану после снятия, график с окрашенными
днями. Тест пишет только свою РК и убирает её."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401 — все таблицы для внешних ключей

from app.ad import boost, build
from app.ad.flight import daily_buckets, flight_of
from app.ad.models import AdCampaign, AdCampaignBoost, AdCampaignPlacement
from app.database import SessionLocal

TODAY = date(2026, 10, 10)


def _fl(start=-10, end=20):
    return flight_of(TODAY + timedelta(days=start), TODAY + timedelta(days=end), today=TODAY)


# ── ввод ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pct", [0, -5, 101, 250])
def test_pct_out_of_range_is_refused(pct):
    with pytest.raises(boost.BoostError, match="(?i)процент"):
        boost.window(_fl(), pct, 3, TODAY)


@pytest.mark.parametrize("days", [0, -1])
def test_days_must_be_positive(days):
    with pytest.raises(boost.BoostError, match="дн"):
        boost.window(_fl(), 20, days, TODAY)


def test_days_beyond_flight_end_are_refused():
    fl = _fl(end=3)                       # после сегодняшнего дня осталось три дня
    assert boost.window(fl, 20, 3, TODAY) == (TODAY, TODAY + timedelta(days=3))
    with pytest.raises(boost.BoostError, match="до конца"):
        boost.window(fl, 20, 4, TODAY)


def test_campaign_not_started_or_finished_is_refused():
    with pytest.raises(boost.BoostError, match="не стартовала"):
        boost.window(_fl(start=2, end=20), 20, 3, TODAY)
    with pytest.raises(boost.BoostError, match="закончилась|нет дней"):
        boost.window(_fl(start=-20, end=-1), 20, 3, TODAY)
    with pytest.raises(boost.BoostError):
        boost.window(None, 20, 3, TODAY)


# ── множитель ───────────────────────────────────────────────────────────────

def _row(i, status="запущен", plan=1000, fixed=None, settled=False):
    return {"id": i, "status": status, "plan_show": plan, "fixed": fixed, "settled": settled}


def test_only_boostable_sites_are_raised_by_pct_of_their_own_rest():
    rows = [_row(1, plan=1500), _row(2, plan=1500),
            _row(3, status="пауза", plan=1000),                 # пауза держит долю, но не крутит
            _row(4, fixed=800, plan=800),                       # заданный объём
            _row(5, settled=True, plan=400),                    # выбыла
            _row(6, status="ждёт запуска", plan=500)]
    facts = {1: 300, 2: 300, 3: 100, 4: 100, 5: 400, 6: 0}
    out, extra = boost.boost_rows(rows, facts, 50)
    got = {r["id"]: r["plan_show"] for r in out}
    assert got[1] == got[2] == 300 + round(1200 * 1.5)           # факт + остаток × 1,5
    assert (got[3], got[4], got[5], got[6]) == (1000, 800, 400, 500)
    assert extra == 2 * 600


def test_without_facts_the_rest_is_the_whole_site_plan_and_never_negative():
    out, extra = boost.boost_rows([_row(1, plan=1000)], None, 10)
    assert out[0]["plan_show"] == 1100 and extra == 100
    out, extra = boost.boost_rows([_row(1, plan=100)], {1: 500}, 10)
    assert out[0]["plan_show"] == 100 and extra == 0              # факт выше плана: остатка нет, план не трогаем


# ── график ──────────────────────────────────────────────────────────────────

def test_chart_marks_boost_days_with_the_extra_part():
    fl = _fl(start=-9, end=20)            # 30 дней, идёт 10-й
    window = (TODAY, TODAY + timedelta(days=2), 50)      # завтра и послезавтра — сегодня уже «отчитан»
    base = daily_buckets(30000, 10000, fl, {}, "day", today=TODAY)
    got = daily_buckets(30000, 10000, fl, {}, "day", today=TODAY, boost=window)
    need = base["need_per_day"]
    by_day = {b["date_from"]: b for b in got["buckets"]}
    for k in (1, 2):                                             # два будущих дня буста
        b = by_day[TODAY + timedelta(days=k)]
        assert b["boost_extra"] == round(need * 0.5)
        assert b["plan"] == round(need * 1.5)
    assert by_day[TODAY]["boost_extra"] == 0                    # сегодняшний день уже в факте
    after = by_day[TODAY + timedelta(days=3)]
    assert after["boost_extra"] == 0
    assert after["plan"] < need                                  # недобор после буста ложится на остальные дни
    # весь остаток по-прежнему закрыт: сумма будущих столбцов == остаток
    assert abs(sum(b["plan"] for b in got["buckets"] if b["date_from"] > TODAY) - 20000) <= 25


def test_chart_without_boost_has_no_extra():
    fl = _fl(start=-9, end=20)
    got = daily_buckets(30000, 10000, fl, {}, "day", today=TODAY)
    assert all(b.get("boost_extra", 0) == 0 for b in got["buckets"])


# ── в базе: раскладка, возврат ──────────────────────────────────────────────

@pytest.fixture
def camp():
    db = SessionLocal()
    deal_id = db.execute(text(
        "SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
        "WHERE c.id IS NULL ORDER BY d.id LIMIT 1")).scalar()
    pubs = [r[0] for r in db.execute(text(
        "SELECT id FROM sales_publishers WHERE status <> 'АРХИВ' ORDER BY id LIMIT 2"))]
    if not deal_id or len(pubs) < 2:
        db.close()
        pytest.skip("нет свободной сделки или двух площадок")
    today = date.today()
    c = AdCampaign(deal_id=deal_id, status="запущена", plan_show=3000,
                   date_start=today - timedelta(days=10), date_end=today + timedelta(days=20))
    db.add(c)
    db.flush()
    pls = []
    for pub in pubs:
        p = AdCampaignPlacement(campaign_id=c.id, publisher_id=pub, weight=1, status="запущен")
        db.add(p)
        pls.append(p)
    db.commit()
    yield db, c, pls
    db.rollback()
    db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": c.id})
    db.commit()
    db.close()


def _plans(db, c, facts):
    _pls, out = build.campaign_layout(db, c.id, facts=facts, facts_given=True)
    return {r["id"]: r["plan_show"] for r in out["rows"]}


def test_boost_raises_the_rest_and_ending_it_gives_the_plan_back(camp):
    db, c, pls = camp
    facts = {pls[0].id: 300, pls[1].id: 300}
    before = _plans(db, c, facts)
    assert set(before.values()) == {1500}
    b = boost.start(db, c, 50, 3, user_id=None, facts=facts, today=date.today())
    db.commit()
    during = _plans(db, c, facts)
    assert set(during.values()) == {2100}                     # остаток 2400 × 1,5 = 3600 → 4200 на РК
    assert b.rest_at_start == 2400 and b.until == date.today() + timedelta(days=3)
    boost.end(db, b, "снят")
    db.commit()
    assert _plans(db, c, facts) == before


def test_second_boost_replaces_the_first(camp):
    db, c, pls = camp
    first = boost.start(db, c, 10, 2, user_id=None, facts=None, today=date.today())
    db.commit()
    second = boost.start(db, c, 30, 4, user_id=None, facts=None, today=date.today())
    db.commit()
    assert db.query(AdCampaignBoost).get(first.id).ended_reason == "заменён"
    assert boost.active(db, c.id).id == second.id


def test_expired_boost_is_ended_by_the_nightly_pass_and_not_applied_after_until(camp):
    db, c, pls = camp
    b = boost.start(db, c, 40, 2, user_id=None, facts=None, today=date.today())
    db.commit()
    # «завтра» первый день после последнего дня буста
    tomorrow_plus = date.today() + timedelta(days=3)
    assert boost.is_live(b, date.today() + timedelta(days=2))
    assert not boost.is_live(b, tomorrow_plus)
    ended = boost.expire_due(db, tomorrow_plus)
    db.commit()
    assert [x.id for x in ended] == [b.id]
    assert db.query(AdCampaignBoost).get(b.id).ended_reason == "истёк"
    assert boost.active(db, c.id) is None


# ── применение, ночь, проверки ──────────────────────────────────────────────

def test_apply_and_cancel_through_the_service(camp, monkeypatch):
    import types
    from app.ad import boost_apply
    db, c, pls = camp
    monkeypatch.setattr(boost_apply, "log_action", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(boost_apply, "_notify", lambda *a, **k: sent.append(a[2]))
    user = types.SimpleNamespace(id=None, name="трафик")
    out = boost_apply.apply(db, c, 30, 3, user)
    assert out["boost"]["pct"] == 30 and out["boost"]["days"] == 3
    assert out["changes"] >= 1 and isinstance(out["external"], list)   # есть ли внешние — зависит от площадок стенда
    assert boost.active(db, c.id) is not None
    out = boost_apply.cancel(db, c, user)
    assert out["boost"] is None and boost.active(db, c.id) is None
    with pytest.raises(boost.BoostError, match="нет"):
        boost_apply.cancel(db, c, user)


def test_nightly_run_closes_expired_boosts_before_it_recounts():
    import inspect
    from app.ad import daily_shares
    src = inspect.getsource(daily_shares.run)
    assert src.index("expire_due") < src.index("refresh_weights"), (
        "истёкший буст закрывается ДО пересчёта: иначе ночь пересчитает по поднятому плану и вернёт его лишь завтра")
    assert src.index("notify_ended") > src.index("sync_limits")


def test_boost_handlers_take_the_shares_lock_before_writing():
    import inspect
    from app.routers import traffic_dashboard as td
    for name in ("boost_start", "boost_cancel"):
        src = inspect.getsource(getattr(td, name))
        assert "_lock_shares(" in src and "_campaign_in_scope(" in src
        assert src.index("_lock_shares(") < src.index("boost_apply."), name


def test_sum_check_does_not_call_a_live_boost_an_overrun():
    from app.bidder.checks import evaluate
    base = {"code": "X", "plan_show": 3000, "date_start": TODAY - timedelta(days=10),
            "date_end": TODAY + timedelta(days=20), "status": "запущена", "in_dsp": True,
            "creatives": 2, "plans": [2100, 2100], "facts": [300, 300]}
    assert any(x["code"] == "sum_mismatch" for x in evaluate([base], True, None, [], TODAY))
    ok = evaluate([{**base, "boost_pct": 50}], True, None, [], TODAY)
    assert not any(x["code"] == "sum_mismatch" for x in ok)


def test_events_are_registered_for_the_traffic_contour():
    from app.notify.registry import EVENTS
    for key in ("traffic_boost_started", "traffic_boost_ended"):
        ev = EVENTS[key]
        assert ev.direction == "traffic"
        assert ev.recipients == [{"type": "staff_group", "value": "traffic"}]


def test_state_gives_the_modal_its_numbers(camp):
    """Окно «Темп размещения» считает прогноз на фронте: сервер отдаёт план, факт, дни, площадки."""
    from app.models import Role, User
    from app.routers import traffic_dashboard as td
    db, c, pls = camp
    admin = db.query(User).join(Role, Role.id == User.role_id).filter(Role.key == "admin").first()
    st = td.boost_state(c.id, db=db, user=admin)
    assert st["plan"] == 3000 and st["days_done"] == 11 and st["days_left"] == 20
    assert st["sites_free"] == 2 and st["sites_fixed"] == 0 and st["can_start"] is True
    assert st["rest_free"] == pytest.approx(3000, abs=2)
    assert {"deal_code", "advertiser", "brand", "service", "fact"} <= set(st)
    boost.start(db, c, 50, 3, user_id=None, facts=None, today=date.today())
    db.commit()
    again = td.boost_state(c.id, db=db, user=admin)
    assert again["rest_free"] == pytest.approx(st["rest_free"], abs=2), "остаток для расчёта — без буста"
    assert again["boost"]["pct"] == 50


# ── правила раскладки против буста (проверка 08.10.2026 по запросу владельца) ──

@pytest.fixture
def camp3():
    """РК на 3 площадки: две крутят, одна на паузе; флайт идёт 11-й день (удержание долей кончилось)."""
    db = SessionLocal()
    deal_id = db.execute(text(
        "SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
        "WHERE c.id IS NULL ORDER BY d.id LIMIT 1")).scalar()
    pubs = [r[0] for r in db.execute(text(
        "SELECT id FROM sales_publishers WHERE status <> 'АРХИВ' ORDER BY id LIMIT 3"))]
    if not deal_id or len(pubs) < 3:
        db.close()
        pytest.skip("нет свободной сделки или трёх площадок")
    today = date.today()
    c = AdCampaign(deal_id=deal_id, status="запущена", plan_show=3000,
                   date_start=today - timedelta(days=10), date_end=today + timedelta(days=20))
    db.add(c)
    db.flush()
    pls = []
    for pub, st in zip(pubs, ("запущен", "запущен", "пауза")):
        p = AdCampaignPlacement(campaign_id=c.id, publisher_id=pub, weight=1, status=st)
        db.add(p)
        pls.append(p)
    db.commit()
    yield db, c, pls
    db.rollback()
    db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": c.id})
    db.commit()
    db.close()


def test_boost_goes_only_to_running_sites_not_to_paused_ones(camp3):
    """Пауза держит долю, но не крутит: добавка буста на неё не уходит, а запущенные получают РОВНО pct %."""
    db, c, pls = camp3
    facts = {pls[0].id: 100, pls[1].id: 100, pls[2].id: 0}
    before = _plans(db, c, facts)
    assert set(before.values()) == {1000}
    boost.start(db, c, 50, 3, user_id=None, facts=facts, today=date.today())
    db.commit()
    during = _plans(db, c, facts)
    assert during[pls[0].id] == during[pls[1].id] == 100 + round(900 * 1.5)
    assert during[pls[2].id] == 1000, "пауза не меняется"


def test_boost_keeps_the_shares_of_raised_sites_and_is_not_blocked_by_the_cap(camp3):
    """Потолок доли буст не зажимает: подъём на один процент остатка у всех касаемых площадок сохраняет их доли
    друг относительно друга. Две запущенные при потолке 34 %: у обеих план поднят, соотношение прежнее."""
    db, c, pls = camp3
    facts = {pls[0].id: 100, pls[1].id: 100, pls[2].id: 0}
    _pls, base = build.campaign_layout(db, c.id, cap_ctx=(0.34, {}), facts=facts, facts_given=True)
    boost.start(db, c, 50, 3, user_id=None, facts=facts, today=date.today())
    db.commit()
    _pls, out = build.campaign_layout(db, c.id, cap_ctx=(0.34, {}), facts=facts, facts_given=True)
    b = {r["id"]: r["plan_show"] for r in base["rows"]}
    a = {r["id"]: r["plan_show"] for r in out["rows"]}
    assert a[pls[0].id] > b[pls[0].id] and a[pls[0].id] == a[pls[1].id]
    assert a[pls[2].id] == b[pls[2].id]


def test_boost_sizes_the_rest_by_last_known_facts_when_fresh_stats_are_missing(camp3):
    """Нет свежей статистики → раскладка по весам, но остаток для буста считается по последним известным фактам:
    иначе pct % брался бы от ВСЕГО плана площадки."""
    db, c, pls = camp3
    for p in pls[:2]:
        db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
                        "VALUES (:c, :p, :d, 300, 0, 'dsp')"),
                   {"c": c.id, "p": p.id, "d": date.today() - timedelta(days=1)})
    db.commit()
    boost.start(db, c, 50, 3, user_id=None, facts=None, today=date.today())
    db.commit()
    _pls, out = build.campaign_layout(db, c.id, facts=None, facts_given=True)
    plans = {r["id"]: r["plan_show"] for r in out["rows"]}
    assert plans[pls[0].id] == 300 + round(700 * 1.5)          # 1000 по весам, факт 300 → остаток 700 × 1,5


def test_effective_pct_for_the_chart_follows_the_boostable_share_of_the_rest():
    assert boost.effective_pct(1000, 500, 40) == pytest.approx(20)
    assert boost.effective_pct(0, 0, 40) == 0
    assert boost.effective_pct(1000, 1000, 40) == 40


def test_recompute_twice_does_not_compound_the_boost(camp3):
    """Ночной прогон и ручные пересчёты идут по ОДНОЙ формуле от исходной раскладки: буст не складывается сам с собой."""
    db, c, pls = camp3
    facts = {pls[0].id: 100, pls[1].id: 100, pls[2].id: 0}
    boost.start(db, c, 50, 3, user_id=None, facts=facts, today=date.today())
    db.commit()
    build.recompute_shares(db, c.id, facts=facts, facts_given=True)
    first = {p.id: p.plan_show for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id)}
    build.recompute_shares(db, c.id, facts=facts, facts_given=True)
    db.expire_all()
    again = {p.id: p.plan_show for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id)}
    assert first == again and first[pls[0].id] == 100 + round(900 * 1.5)


def test_in_the_hold_period_only_running_sites_are_boosted_and_the_waiting_keep_their_share(camp3):
    """Первые 5 дней объём делят все площадки в работе; буст поднимает только запущенную, ждущая не меняется."""
    db, c, pls = camp3
    c.date_start = date.today() - timedelta(days=2)
    pls[1].status, pls[2].status = "ждёт запуска", "ждёт сборки"
    db.commit()
    base = _plans(db, c, None)
    boost.start(db, c, 50, 3, user_id=None, facts=None, today=date.today())
    db.commit()
    during = _plans(db, c, None)
    assert during[pls[0].id] == round(base[pls[0].id] * 1.5)
    assert during[pls[1].id] == base[pls[1].id] and during[pls[2].id] == base[pls[2].id]


def test_the_journal_names_the_boost_as_the_reason_not_the_weight(camp3):
    from app.bidder.rules import REASONS, RULES, explain
    db, c, pls = camp3
    boost.start(db, c, 50, 3, user_id=None, facts={}, today=date.today())
    db.commit()
    changes = build.recompute_shares(db, c.id, facts={}, facts_given=True)
    why = {x["placement_id"]: x["reason"] for x in changes}
    assert why[pls[0].id] == why[pls[1].id] == "boost"           # запущенные подняты бустом
    assert why[pls[2].id] == "weight"                           # пауза — по весу, буст её не трогал
    assert "boost" in REASONS and any("Темп размещения" in r["title"] for r in RULES)
    assert explain({"boosted": True, "in_plan": True, "plan_show": 10}, 0, False, None)["code"] == "boost"
