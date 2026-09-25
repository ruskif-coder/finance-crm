"""Посадочная и запрос ссылки — у пары «креатив × площадка» (владелец 25.09.2026).

У разных креативов одной площадки в одной РК посадочные бывают разные. Пока посадочная
жила на площадке сделки, креатив №2 получал посадочную креатива №1 («автозаполнение»),
запрос ссылки по креативу №1 запирал «ок» по креативу №2, а ссылка из кабинета ложилась
не в тот креатив.
"""
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet,
                                    LaunchPrepPair, LaunchPrepReview, LaunchPrepSetTarget)
from app.routers import launch_prep as lp
from app.routers import traffic
from tests.test_launch_prep_pairs import NO_BASE, _ADMIN, env  # noqa: F401


def _second_set(env, url=None):  # noqa: F811
    """Второй креатив той же сделки на тех же площадках — БЕЗ посадочных."""
    s = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 7)
    env.db.add(s)
    env.db.flush()
    for t in env.targets:
        env.db.add(LaunchPrepSetTarget(set_id=s.id, target_id=t.id, advertiser_url=url))
    env.db.add(LaunchPrepCreativeFile(set_id=s.id, path='creatives/t7.png',
                                      original_name='t7.png', size_bytes=10))
    env.db.add(LaunchPrepReview(set_id=s.id, kind='первичная_тт', verdict='ок',
                                source='аккаунт', decided_by='тест'))
    env.db.commit()
    return s


def _row(env, set_id, target_id):  # noqa: F811
    tree = lp.deal_creatives(env.deal.id, env.db, _ADMIN)
    s = next(x for x in tree["sets"] if x["id"] == set_id)
    return next(r for r in s["recipients"] if r["target_id"] == target_id)


def test_landing_of_one_creative_does_not_fill_another(env):  # noqa: F811
    second = _second_set(env)
    t = env.targets[0]
    lp.set_member_url(env.cset.id, t.id, lp.TargetUrlIn(url='https://a.test/one'),
                      env.db, _ADMIN)
    assert _row(env, env.cset.id, t.id)["advertiser_url"] == 'https://a.test/one'
    other = _row(env, second.id, t.id)
    assert other["advertiser_url"] is None, "посадочная креатива №1 подставилась в №2"
    assert other["url_state"] == "нужна"


def test_send_requires_landing_of_this_creative(env):  # noqa: F811
    """Посадочная креатива №1 не засчитывается креативу №2 при отправке."""
    second = _second_set(env)
    with pytest.raises(HTTPException) as e:
        lp.send_set(second.id, lp.SendIn(), env.db, _ADMIN)
    assert "посадочн" in e.value.detail.lower()
    for t in env.targets:
        lp.set_member_url(second.id, t.id, lp.TargetUrlIn(url='https://b.test/two'),
                          env.db, _ADMIN)
    lp.send_set(second.id, lp.SendIn(), env.db, _ADMIN)


def test_url_request_belongs_to_its_creative(env):  # noqa: F811
    second = _second_set(env)
    t = env.targets[0]
    out = lp.request_member_url(second.id, t.id, lp.UrlRequestIn(text='дайте ссылку'),
                                env.db, _ADMIN)
    assert out["url_state"] == "запрошена"
    assert _row(env, second.id, t.id)["url_state"] == "запрошена"
    assert _row(env, env.cset.id, t.id)["url_state"] == "есть", "запрос ушёл не в тот креатив"


def test_request_is_refused_when_this_creative_has_a_landing(env):  # noqa: F811
    with pytest.raises(HTTPException):
        lp.request_member_url(env.cset.id, env.targets[0].id,
                              lp.UrlRequestIn(text='дайте ссылку'), env.db, _ADMIN)


def test_bad_scheme_is_refused(env):  # noqa: F811
    with pytest.raises(HTTPException):
        lp.set_member_url(env.cset.id, env.targets[0].id,
                          lp.TargetUrlIn(url='javascript:alert(1)'), env.db, _ADMIN)


def test_urls_for_erid_come_from_the_creative(env):  # noqa: F811
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    second = _second_set(env, url='https://b.test/two')
    lp.send_set(second.id, lp.SendIn(), env.db, _ADMIN)
    assert set(lp._target_urls(env.db, env.cset.id)) == {'https://site.test/tovar/1'}
    assert set(lp._target_urls(env.db, second.id)) == {'https://b.test/two'}


def test_traffic_queue_shows_landing_of_the_creative(env, monkeypatch):  # noqa: F811
    from app.dsp import targeting_creative as tc
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    second = _second_set(env, url='https://b.test/two')
    lp.send_set(second.id, lp.SendIn(), env.db, _ADMIN)
    rows = traffic.queue('all', env.db, _ADMIN)["rows"]
    by_set = {}
    for r in rows:
        by_set.setdefault(r["set"]["id"], set()).add(r["advertiser_url"])
    assert by_set[env.cset.id] == {'https://site.test/tovar/1'}
    assert by_set[second.id] == {'https://b.test/two'}


def test_open_request_blocks_ok_only_in_its_creative(env, monkeypatch):  # noqa: F811
    from app.dsp import targeting_creative as tc
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    second = _second_set(env, url='https://b.test/two')
    lp.send_set(second.id, lp.SendIn(), env.db, _ADMIN)
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    # Запрос открыт у креатива №1 — «ок» по креативу №2 он держать не должен.
    m = env.db.query(LaunchPrepSetTarget).filter(
        LaunchPrepSetTarget.set_id == env.cset.id,
        LaunchPrepSetTarget.target_id == env.targets[0].id).first()
    m.advertiser_url, m.url_requested_at = None, datetime.now()
    env.db.commit()
    pair2 = env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == second.id,
        LaunchPrepPair.target_id == env.targets[0].id).first()
    # Трафик пропускает — это и открывает вопрос площадке.
    traffic.pair_verdict(pair2.id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    lp.pair_verdict(pair2.id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)


# ── плановый объём показов по площадке креатива (п. 6, владелец 25.09.2026) ─────
#
# Объём креатива на площадке и СУММА всех заданных объёмов по креативам сделки не могут
# быть больше плана РК: «напишут миллион, а план 500 тысяч на всю РК».

def _plan(monkeypatch, value):
    from app.ad import build
    monkeypatch.setattr(build, "deal_plan", lambda db, deal_id: {"plan_show": value})


def test_plan_volume_is_saved_per_creative(env, monkeypatch):  # noqa: F811
    _plan(monkeypatch, 500000)
    t = env.targets[0]
    out = lp.set_member_plan(env.cset.id, t.id, lp.PlanIn(plan_show=180000), env.db, _ADMIN)
    assert out["plan_show"] == 180000
    assert _row(env, env.cset.id, t.id)["plan_show"] == 180000


def test_plan_volume_above_rk_plan_is_refused(env, monkeypatch):  # noqa: F811
    _plan(monkeypatch, 500000)
    with pytest.raises(HTTPException) as e:
        lp.set_member_plan(env.cset.id, env.targets[0].id, lp.PlanIn(plan_show=1000000),
                           env.db, _ADMIN)
    assert e.value.status_code == 400 and "500" in e.value.detail


def test_sum_over_creatives_above_rk_plan_is_refused(env, monkeypatch):  # noqa: F811
    _plan(monkeypatch, 500000)
    second = _second_set(env)
    lp.set_member_plan(env.cset.id, env.targets[0].id, lp.PlanIn(plan_show=300000),
                       env.db, _ADMIN)
    with pytest.raises(HTTPException) as e:
        lp.set_member_plan(second.id, env.targets[1].id, lp.PlanIn(plan_show=250000),
                           env.db, _ADMIN)
    assert "200" in e.value.detail, "отказ обязан назвать, сколько ещё можно распределить"
    # замена своего же значения не считается дважды
    lp.set_member_plan(env.cset.id, env.targets[0].id, lp.PlanIn(plan_show=250000),
                       env.db, _ADMIN)
    lp.set_member_plan(second.id, env.targets[1].id, lp.PlanIn(plan_show=250000),
                       env.db, _ADMIN)


def test_plan_volume_can_be_cleared_and_must_not_be_negative(env, monkeypatch):  # noqa: F811
    _plan(monkeypatch, 500000)
    t = env.targets[0]
    lp.set_member_plan(env.cset.id, t.id, lp.PlanIn(plan_show=1000), env.db, _ADMIN)
    out = lp.set_member_plan(env.cset.id, t.id, lp.PlanIn(plan_show=None), env.db, _ADMIN)
    assert out["plan_show"] is None
    with pytest.raises(HTTPException):
        lp.set_member_plan(env.cset.id, t.id, lp.PlanIn(plan_show=-5), env.db, _ADMIN)


def test_deal_tree_carries_rk_plan(env, monkeypatch):  # noqa: F811
    _plan(monkeypatch, 500000)
    tree = lp.deal_creatives(env.deal.id, env.db, _ADMIN)
    assert tree["rk_plan_show"] == 500000
