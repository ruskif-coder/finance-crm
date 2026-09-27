"""Объёмы по площадкам против плана РК (владелец 27.09.2026).

  · сумма объёмов одной площадки > 50 % плана РК — предупреждение, без блокировки;
  · больше 100 % (у площадки или в сумме по всем) — блокировка дальнейших действий:
    отправки трафику, «Изменить стадию», запуска РК и площадок — с уведомлением.

При вводе объёма > 100 % не пропускается уже сейчас; превышение появляется, когда объёмы
уже вписаны, а план в медиаплане потом уменьшили.
"""
from app.launch_prep import volumes
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401


def test_levels_from_numbers():
    st = volumes.evaluate(1000, {1: 300, 2: 510})
    assert st["by_publisher"][1]["level"] == "ok"
    assert st["by_publisher"][2]["level"] == "warn"
    assert st["blocked"] is False
    assert st["total"] == 810


def test_over_the_plan_in_total_blocks():
    st = volumes.evaluate(1000, {1: 600, 2: 600})
    assert st["blocked"] is True
    assert st["over_by"] == 200
    assert "превышают план РК на 200" in st["message"]


def test_one_publisher_over_the_plan_blocks():
    st = volumes.evaluate(500, {1: 700})
    assert st["by_publisher"][1]["level"] == "over"
    assert st["blocked"] is True


def test_exactly_half_is_not_a_warning_and_exactly_the_plan_is_not_over():
    st = volumes.evaluate(1000, {1: 500, 2: 500})
    assert {v["level"] for v in st["by_publisher"].values()} == {"ok"}
    assert st["blocked"] is False


def test_fractional_plan_is_rounded_like_the_input_check():
    """CPC: показы из кликов через CTR дробные. При вводе план округляется
    (`launch_prep._rk_plan`) — принятое там 100 000 не может стать «больше плана» здесь."""
    st = volumes.evaluate(99999.6, {1: 100000})
    assert st["blocked"] is False and st["plan"] == 100000


def test_unknown_plan_checks_nothing():
    st = volumes.evaluate(None, {1: 10 ** 9})
    assert st["blocked"] is False and st["by_publisher"][1]["level"] == "ok"


def test_send_to_traffic_is_blocked_when_volumes_exceed_the_plan(env, monkeypatch):  # noqa: F811
    import pytest
    from fastapi import HTTPException
    from app.ad import build as ad_build
    from app.launch_prep.models import LaunchPrepPair, LaunchPrepSetTarget
    from app.routers import launch_prep as lp
    monkeypatch.setattr(ad_build, "deal_plan", lambda db, d: {"plan_show": 1000})
    m = env.db.query(LaunchPrepSetTarget).filter(
        LaunchPrepSetTarget.set_id == env.cset.id).first()
    m.plan_show = 1200                  # план РК уменьшили уже после ввода объёма
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    assert e.value.status_code == 400 and "превышают план РК на 200" in e.value.detail
    assert not env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == env.cset.id).count(), "отказ после записи"


def test_every_further_action_asks_the_same_guard():
    """Отправка, запуск РК и площадки, выгрузка в DSP — одна проверка. Стадия — через
    расчёт перехода `plan_move` (ниже), а не в одном диалоге."""
    import inspect
    from app.routers import launch_prep as lp, traffic_dashboard as td
    for fn in (lp.send_set, td.set_campaign_status, td.set_placement_status, td.run_dsp):
        assert "volumes.guard(" in inspect.getsource(fn), fn.__name__


# ── стадия: запрет живёт в расчёте перехода, а не в диалоге ─────────────────────
#
# Ревью 27.09.2026: `volumes.guard` стоял в `move_deal` до выбора цели и запирал ЛЮБОЙ
# перевод — назад, в «сорвалась», в архив; а массовая правка реестра и автоматика
# (привязка МП, «Завершить РК») двигали стадию мимо него. Расчёт перехода `plan_move`
# общий для всех путей, поэтому превышение — строка-блокер в нём: вперёд не пускает,
# назад и в терминал пускает, мастер проводит с причиной — как любое требование.

def _move_env(monkeypatch, blocked):
    from types import SimpleNamespace as NS
    from app.sales import stage_move, stage_scope, stage_checks as sc
    monkeypatch.setattr(stage_scope, "stage_services", lambda db: {})
    monkeypatch.setattr(stage_scope, "stage_applies", lambda sid, deal, marks: True)
    monkeypatch.setattr(stage_move, "checks_for", lambda db, sid: [])
    monkeypatch.setattr(sc, "evaluate", lambda db, deal, rows: [])
    monkeypatch.setattr(volumes, "check", lambda db, deal_id: {
        "blocked": blocked, "message": "Объёмы по площадкам превышают план РК на 200 показов"})
    cur = NS(id=1, is_terminal=False, phase=None)
    fwd = NS(id=2, is_terminal=False, phase=None)
    back = NS(id=0, is_terminal=False, phase=None)
    lost = NS(id=9, is_terminal=True, phase=None)
    order = [0, 1, 2]
    cat = NS(by_id={1: cur, 2: fwd, 0: back, 9: lost},
             is_before=lambda a, b: a in order and b in order and order.index(a) < order.index(b))
    deal = NS(id=7, our_stage_id=1, realization_pipeline_id=1)
    return stage_move, deal, cat, fwd, back, lost


def test_forward_move_is_blocked_while_volumes_exceed_the_plan(monkeypatch):
    stage_move, deal, cat, fwd, back, lost = _move_env(monkeypatch, blocked=True)
    plan = stage_move.plan_move(None, deal, fwd, cat)
    assert not plan.allowed
    assert any("превышают план РК" in (ln.result.detail or "") for ln in plan.blockers)


def test_back_and_terminal_moves_pass_despite_the_excess(monkeypatch):
    """Сделку с превышением можно вернуть назад и объявить сорвавшейся."""
    stage_move, deal, cat, fwd, back, lost = _move_env(monkeypatch, blocked=True)
    assert stage_move.plan_move(None, deal, back, cat).allowed
    assert stage_move.plan_move(None, deal, lost, cat).allowed


def test_no_excess_no_extra_line(monkeypatch):
    stage_move, deal, cat, fwd, back, lost = _move_env(monkeypatch, blocked=False)
    plan = stage_move.plan_move(None, deal, fwd, cat)
    assert plan.allowed and plan.lines == []


def test_notification_goes_out_only_when_the_excess_appears(env, monkeypatch):  # noqa: F811
    """Уведомление — в момент появления превышения, не на каждом сохранении."""
    from app.ad import build as ad_build
    from app.launch_prep.models import LaunchPrepSetTarget
    from app.notify import bus
    sent = []
    monkeypatch.setattr(bus, "emit", lambda db, key, **k: sent.append((key, k)) or [])
    plan = {"v": 2000}
    monkeypatch.setattr(ad_build, "deal_plan", lambda db, d: {"plan_show": plan["v"]})
    m = env.db.query(LaunchPrepSetTarget).filter(
        LaunchPrepSetTarget.set_id == env.cset.id).first()
    m.plan_show = 1200
    env.db.commit()
    before = volumes.check(env.db, env.deal.id)
    assert before["blocked"] is False
    plan["v"] = 1000                                   # план уменьшили
    assert volumes.notify_if_newly_blocked(env.db, env.deal.id, before, _ADMIN) is True
    assert sent and sent[0][0] == "volumes_over_plan"
    assert "превышают план РК на 200" in sent[0][1]["body"]
    again = volumes.check(env.db, env.deal.id)
    assert volumes.notify_if_newly_blocked(env.db, env.deal.id, again, _ADMIN) is False
    assert len(sent) == 1, "повторное сохранение с тем же превышением шумит"


# ── какие объёмы держат план (ревью 27.09.2026) ─────────────────────────────────
#
# Раскладка РК (`ad/build.PLACEMENT_FIXED_SQL`) не считает креативы, отклонённые
# площадкой, а проверка объёмов считала все. Отклонили креатив с 600 тысячами, дали
# столько же доработке — проверка видела 1,2 млн при плане в миллион и запирала сделку,
# хотя РК распределяла 600 тысяч. Правило одно: отклонённый объём плана не держит.

def test_rejected_creative_volume_does_not_hold_the_plan(env, monkeypatch):  # noqa: F811
    from app.ad import build as ad_build
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    from app.launch_prep.models import LaunchPrepPair, LaunchPrepSetTarget
    db = env.db
    monkeypatch.setattr(ad_build, "deal_plan", lambda db_, d: {"plan_show": 1000})
    for m in db.query(LaunchPrepSetTarget).filter(LaunchPrepSetTarget.set_id == env.cset.id):
        m.plan_show = 600
    db.commit()
    assert volumes.check(db, env.deal.id)["blocked"] is True

    rejected = env.targets[0]
    pair = LaunchPrepPair(set_id=env.cset.id, target_id=rejected.id)
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == env.deal.id).first()
    own_camp = camp is None
    if own_camp:
        camp = AdCampaign(deal_id=env.deal.id)
        db.add(camp)
    db.add(pair)
    db.flush()
    pl = AdCampaignPlacement(campaign_id=camp.id, publisher_id=rejected.publisher_id)
    db.add(pl)
    db.flush()
    db.add(AdCampaignCreative(campaign_id=camp.id, placement_id=pl.id, pair_id=pair.id,
                              creative_no=1, status=ad_build.CREATIVE_REJECTED))
    db.commit()
    try:
        st = volumes.check(db, env.deal.id)
        assert st["blocked"] is False, st["message"]
        assert st["total"] == 600
    finally:
        db.query(AdCampaignCreative).filter(AdCampaignCreative.pair_id == pair.id).delete()
        db.query(AdCampaignPlacement).filter(AdCampaignPlacement.id == pl.id).delete()
        if own_camp:
            db.query(AdCampaign).filter(AdCampaign.id == camp.id).delete()
        db.commit()


def test_a_volume_can_always_be_reduced(env, monkeypatch):  # noqa: F811
    """План РК урезали — объёмы уже больше него. Уменьшать их надо давать по одному:
    уменьшение положение только исправляет. До ревью 27.09.2026 ввод отказывал, пока
    ОСТАЛЬНЫЕ сами превышали план, и снять превышение можно было только очисткой поля."""
    from app.ad import build as ad_build
    from app.launch_prep.models import LaunchPrepSetTarget
    from app.routers import launch_prep as lp
    monkeypatch.setattr(ad_build, "deal_plan", lambda db, d: {"plan_show": 1000})
    monkeypatch.setattr(ad_build, "sync_deal_quietly", lambda db, d: None)
    monkeypatch.setattr(lp, "log_action", lambda *a, **k: None)
    a, b = env.targets
    for t, v in ((a, 900), (b, 900)):
        env.db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id == env.cset.id,
            LaunchPrepSetTarget.target_id == t.id).update({"plan_show": v})
    env.db.commit()
    out = lp.set_member_plan(env.cset.id, a.id, lp.PlanIn(plan_show=500), env.db, _ADMIN)
    assert out["plan_show"] == 500
