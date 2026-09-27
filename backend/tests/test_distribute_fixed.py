"""Заданный объём площадки по креативу → в РК как плановый, остаток по весам (владелец,
п. 6 списка 25.09.2026).

Объём вводится в блоке креатива на паре «креатив × площадка»; ввод уже проверяет, что ни
одно значение и их сумма не превышают план РК. Здесь — как он ложится в раскладку:

  · площадка в плане с заданным объёмом получает РОВНО его (сумму по её креативам);
  · остаток плана РК делится по весам между остальными площадками в плане;
  · выключенная площадка свой объём не держит — он возвращается в общий остаток;
  · внутри площадки креатив с объёмом получает его, остаток — поровну остальным.
"""
from app.ad.flight import distribute, split_evenly
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401

ON = "запущен"
OFF = "ждёт сборки"


def _rows(out):
    return {r["id"]: r for r in out["rows"]}


def test_fixed_placement_gets_exactly_its_volume_and_the_rest_goes_by_weight():
    out = distribute(1000, None, None, [
        {"id": 1, "status": ON, "weight": 1, "fixed": 300},
        {"id": 2, "status": ON, "weight": 1},
        {"id": 3, "status": ON, "weight": 3},
    ])
    r = _rows(out)
    assert r[1]["plan_show"] == 300 and r[1]["fixed"] == 300
    assert r[2]["plan_show"] == 175 and r[3]["plan_show"] == 525      # 700 → 1 : 3
    assert sum(x["plan_show"] for x in out["rows"]) == 1000
    assert abs(out["share_sum"] - 1.0) < 1e-6


def test_switched_off_placement_returns_its_volume_to_the_pool():
    r = _rows(distribute(1000, None, None, [
        {"id": 1, "status": OFF, "weight": 1, "fixed": 300},
        {"id": 2, "status": ON, "weight": 1},
    ]))
    assert r[1]["plan_show"] is None
    assert r[2]["plan_show"] == 1000


def test_without_fixed_nothing_changes():
    r = _rows(distribute(1000, None, None, [
        {"id": 1, "status": ON, "weight": 1}, {"id": 2, "status": ON, "weight": 3}]))
    assert (r[1]["plan_show"], r[2]["plan_show"]) == (250, 750)
    assert not r[1]["fixed"] and not r[2]["fixed"]


def test_fixed_placement_without_weight_still_gets_its_volume():
    """Индекса в балансировщике нет — а объём задан руками: он и есть план площадки."""
    r = _rows(distribute(1000, None, None, [
        {"id": 1, "status": ON, "weight": None, "fixed": 200},
        {"id": 2, "status": ON, "weight": 1}]))
    assert r[1]["plan_show"] == 200 and r[2]["plan_show"] == 800


def test_creatives_fixed_first_the_rest_evenly():
    out = split_evenly(1000, [
        {"id": 1, "creative_no": 1, "status": ON, "fixed": 400},
        {"id": 2, "creative_no": 2, "status": ON},
        {"id": 3, "creative_no": 3, "status": ON},
    ])
    plans = {c["id"]: c["plan_show"] for c in out}
    assert plans == {1: 400, 2: 300, 3: 300}
    assert sum(plans.values()) == 1000


def test_volume_entered_on_the_creative_lands_in_the_campaign(env):  # noqa: F811
    """Вся цепочка: объём на паре «креатив × площадка» → сохранённая доля РК."""
    from sqlalchemy import text
    from app.ad import build
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    from app.launch_prep.models import LaunchPrepPair, LaunchPrepSetTarget
    from app.routers import launch_prep as lp

    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    camp = AdCampaign(deal_id=env.deal.id, status="запущена", plan_show=1000)
    env.db.add(camp)
    env.db.flush()
    try:
        pls = {}
        for t in env.targets:
            pls[t.id] = AdCampaignPlacement(campaign_id=camp.id, publisher_id=t.publisher_id,
                                            status=ON, weight=1)
            env.db.add(pls[t.id])
        env.db.flush()
        for pr in env.db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == env.cset.id):
            env.db.add(AdCampaignCreative(campaign_id=camp.id, placement_id=pls[pr.target_id].id,
                                          root_set_id=env.cset.id, pair_id=pr.id,
                                          creative_no=1, status=ON))
        first = env.targets[0]
        env.db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id == env.cset.id,
            LaunchPrepSetTarget.target_id == first.id).update({"plan_show": 300})
        env.db.flush()
        build.recompute_shares(env.db, camp.id)
        env.db.flush()
        got = {t.id: pls[t.id].plan_show for t in env.targets}
        assert got[first.id] == 300
        assert got[env.targets[1].id] == 700
    finally:
        env.db.rollback()
        env.db.execute(text("DELETE FROM ad_campaign_creative WHERE campaign_id = :c"), {"c": camp.id})
        env.db.execute(text("DELETE FROM ad_campaign_placement WHERE campaign_id = :c"), {"c": camp.id})
        env.db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        env.db.commit()


def test_without_a_plan_shares_still_follow_the_weights():
    """РК без плана (медиаплан только с Фиксом): доля площадки — по весам, как до
    объёмов. Ревью 27.09.2026 нашло, что доля стала нулём у всех: колонка «доля» на
    дашборде и в карточке показывала прочерк, `recompute_shares` писал None."""
    out = distribute(None, None, None, [
        {"id": 1, "status": ON, "weight": 1}, {"id": 2, "status": ON, "weight": 3}])
    r = _rows(out)
    assert (r[1]["share"], r[2]["share"]) == (0.25, 0.75)
    assert r[1]["plan_show"] is None and abs(out["share_sum"] - 1.0) < 1e-6


def test_small_total_gives_zero_not_none_to_the_last_creatives():
    """Показов меньше, чем креативов: последний получает 0, как до объёмов, а не None."""
    out = split_evenly(2, [{"id": i, "creative_no": i, "status": ON} for i in (1, 2, 3)])
    assert [c["plan_show"] for c in out] == [1, 1, 0]


def test_rejecting_a_creative_by_hand_rebuilds_the_placement_plans(env, monkeypatch):  # noqa: F811
    """Отклонённый креатив объём площадки не держит (`PLACEMENT_FIXED_SQL`). Отклонил
    трафик руками — планы площадок обязаны пересчитаться сразу, а не ждать следующей
    сборки: иначе DSP и дашборд крутят по устаревшему фиксу (ревью 27.09.2026)."""
    from sqlalchemy import text
    from app.ad import build
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    from app.launch_prep.models import LaunchPrepPair, LaunchPrepSetTarget
    from app.routers import launch_prep as lp, traffic_dashboard as td

    monkeypatch.setattr(td, "log_action", lambda *a, **k: None)
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    camp = AdCampaign(deal_id=env.deal.id, status="запущена", plan_show=1000)
    env.db.add(camp)
    env.db.flush()
    try:
        pls = {}
        for t in env.targets:
            pls[t.id] = AdCampaignPlacement(campaign_id=camp.id, publisher_id=t.publisher_id,
                                            status=ON, weight=1)
            env.db.add(pls[t.id])
        env.db.flush()
        crs = {}
        for pr in env.db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == env.cset.id):
            crs[pr.target_id] = AdCampaignCreative(
                campaign_id=camp.id, placement_id=pls[pr.target_id].id, root_set_id=env.cset.id,
                pair_id=pr.id, creative_no=1, status=ON)
            env.db.add(crs[pr.target_id])
        first = env.targets[0]
        env.db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id == env.cset.id,
            LaunchPrepSetTarget.target_id == first.id).update({"plan_show": 300})
        env.db.flush()
        build.recompute_shares(env.db, camp.id)
        env.db.commit()
        assert pls[first.id].plan_show == 300

        td.set_creative_status(crs[first.id].id, td.StatusIn(status=build.CREATIVE_REJECTED),
                               db=env.db, user=_ADMIN)
        env.db.refresh(pls[first.id])
        assert pls[first.id].plan_show == 500, "фикс отклонённого креатива держит план"
    finally:
        env.db.rollback()
        env.db.execute(text("DELETE FROM ad_campaign_creative WHERE campaign_id = :c"), {"c": camp.id})
        env.db.execute(text("DELETE FROM ad_campaign_placement WHERE campaign_id = :c"), {"c": camp.id})
        env.db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
        env.db.commit()
