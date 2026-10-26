"""Ручной план площадки (`fixed_plan`, «Перераспределить», 24.10.2026) и балансировщик — на живой РК стенда.

Ночной пересчёт по индексам (`refresh_weights`) ручной план не перетирает; остальные площадки делят остаток по весам;
сумма планов = план РК; снятие ручных планов возвращает раскладку по весам; площадка с ручным планом, ушедшая со
статуса «в плане», объём не держит. Состояние РК после теста возвращается как было."""
import pytest
from sqlalchemy import text

from app.ad import build
from app.ad.models import AdCampaign, AdCampaignPlacement
from app.database import SessionLocal


@pytest.fixture
def rk():
    db = SessionLocal()
    cid = db.execute(text("""
        SELECT c.id FROM ad_campaign c JOIN ad_campaign_placement p ON p.campaign_id = c.id
         WHERE c.status NOT IN ('окончена', 'архив') AND c.plan_show > 0 AND c.date_start IS NOT NULL
         GROUP BY c.id HAVING count(*) FILTER (WHERE p.status = 'запущен' AND p.weight > 0) >= 3
         ORDER BY c.id LIMIT 1""")).scalar()
    if cid is None:
        db.close()
        pytest.skip("на стенде нет РК с тремя запущенными площадками")
    saved = {p.id: (p.plan_show, p.share, p.fixed_plan, p.status)
             for p in db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == cid)}
    run_from = db.execute(text("SELECT coalesce(max(id), 0) FROM bidder_run")).scalar()
    yield db, db.get(AdCampaign, cid)
    db.rollback()
    for p in db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == cid):
        p.plan_show, p.share, p.fixed_plan, p.status = saved[p.id]
    db.execute(text("DELETE FROM bidder_run WHERE id > :r"), {"r": run_from})
    db.commit()
    db.close()


def _pls(db, cid):
    db.expire_all()
    return {p.id: p for p in db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == cid)}


def test_nightly_balancer_keeps_manual_plans_and_the_sum(rk):
    db, camp = rk
    build.recompute_shares(db, camp.id)
    db.commit()
    pls = _pls(db, camp.id)
    run = sorted((p for p in pls.values() if p.status == "запущен" and p.weight and p.plan_show),
                 key=lambda p: p.id)[:3]
    a, b, others = run[0], run[1], run[2]
    move = round(min(a.plan_show, b.plan_show) * 0.2)
    a_new, b_new = round(a.plan_show) - move, round(b.plan_show) + move
    other_before = others.plan_show
    a.fixed_plan, b.fixed_plan = a_new, b_new
    db.flush()
    build.recompute_shares(db, camp.id)
    db.commit()
    build.refresh_weights(db, campaign_ids=[camp.id])     # ночной путь
    pls = _pls(db, camp.id)
    assert round(pls[a.id].plan_show) == max(a_new, 0) or pls[a.id].plan_show >= a_new, "ручной план донора перетёрт"
    assert round(pls[b.id].plan_show) == b_new, "ручной план получателя перетёрт ночным пересчётом"
    assert abs(pls[others.id].plan_show - other_before) <= max(2, other_before * 0.01), "остальные сдвинулись"
    in_plan = [p.plan_show or 0 for p in pls.values() if p.status in ("запущен", "пауза")]
    assert abs(sum(in_plan) - camp.plan_show) <= len(in_plan) + 1

    # площадка с ручным планом ушла из плана — её объём возвращается остальным
    pls[b.id].status = "завершена"
    db.flush()
    build.recompute_shares(db, camp.id)
    db.commit()
    pls = _pls(db, camp.id)
    assert pls[others.id].plan_show > other_before


def test_reset_returns_to_weights(rk):
    from app.ad import realloc

    class _Ms:
        def last_sent_show_limit(self, ref):
            return None

        def creative_edit(self, *a, **k):
            return True

    db, camp = rk
    build.recompute_shares(db, camp.id)
    db.commit()
    before = {i: p.plan_show for i, p in _pls(db, camp.id).items()}
    first = next(p for p in _pls(db, camp.id).values() if p.status == "запущен" and p.plan_show)
    realloc.apply(db, camp, {first.id: round(first.plan_show * 0.9)}, None, client=_Ms())
    assert _pls(db, camp.id)[first.id].fixed_plan is not None
    realloc.reset(db, camp, client=_Ms())
    after = {i: p.plan_show for i, p in _pls(db, camp.id).items()}
    assert all(p.fixed_plan is None for p in _pls(db, camp.id).values())
    assert all(abs((after[i] or 0) - (before[i] or 0)) <= 1 for i in before)


def test_routes_preview_refuse_and_apply(rk, monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.ad import boost_apply
    from app.models import AuditLog
    from app.routers import traffic_dashboard as td
    monkeypatch.setattr(boost_apply, "_sync", lambda db, camp, client: {"updated": 0, "failed": [], "zero": []})
    db, camp = rk
    admin = SimpleNamespace(role=SimpleNamespace(key="admin"), id=None, name="тест", role_id=None)
    try:
        v = td.realloc_preview(camp.id, db, admin)
        assert {"rows", "moved", "unplaced", "days_left", "has_manual"} <= set(v)
        r = next(x for x in v["rows"] if x["running"] and x["fact"] > 0)
        with pytest.raises(HTTPException) as e:          # без причины не применяется (хендофф 26.10.2026)
            td.realloc_apply(camp.id, td.ReallocIn(plans={str(r["id"]): r["plan"]}), db, admin)
        assert e.value.status_code == 400 and "причин" in e.value.detail
        with pytest.raises(HTTPException) as e:
            td.realloc_apply(camp.id, td.ReallocIn(plans={str(r["id"]): r["fact"] - 1}, reason="тест"), db, admin)
        assert e.value.status_code == 400 and "открученного" in e.value.detail
        with pytest.raises(HTTPException):
            td.realloc_apply(camp.id, td.ReallocIn(plans={str(r["id"]): camp.plan_show * 2}, reason="тест"), db, admin)
        out = td.realloc_apply(camp.id, td.ReallocIn(plans={str(r["id"]): r["plan"]}, reason="тест"), db, admin)
        assert out["view"]["has_manual"] is True
        out = td.realloc_reset(camp.id, db, admin)
        assert out["view"]["has_manual"] is False
    finally:
        db.rollback()
        db.query(AuditLog).filter(AuditLog.action.in_(("traffic_realloc", "traffic_realloc_reset")),
                                  AuditLog.details.like("%")).filter(AuditLog.user_id.is_(None)).delete(
            synchronize_session=False)
        db.commit()


def test_realloc_is_refused_while_boost_is_live(rk, monkeypatch):
    """Под бустом записанные планы подняты на его процент: записать их ручными — значит продлить буст навсегда и
    перекрутить план РК. Пока буст идёт — отказ с подсказкой снять его."""
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.ad import boost as boost_mod
    from app.routers import traffic_dashboard as td
    db, camp = rk
    monkeypatch.setattr(boost_mod, "active", lambda db, cid: SimpleNamespace(pct=20))
    monkeypatch.setattr(boost_mod, "is_live", lambda b, today=None: True)
    admin = SimpleNamespace(role=SimpleNamespace(key="admin"), id=None, name="тест", role_id=None)
    with pytest.raises(HTTPException) as e:
        td.realloc_apply(camp.id, td.ReallocIn(plans={"1": 1}), db, admin)
    assert e.value.status_code == 400 and "буст" in e.value.detail.lower()
    assert td.realloc_preview(camp.id, db, admin)["boost_live"] is True


def test_plan_cut_below_manual_plans_notifies_and_offers_reset(rk, monkeypatch):
    """Медиаплан урезали ниже ручных планов: трафику уведомление (одно), в окне — плашка и сброс; планы не трогаются."""
    from app.ad import realloc
    from app.notify import bus
    from app.routers.traffic_dashboard import _realloc_view
    db, c = rk
    sent = []
    monkeypatch.setattr(bus, "emit", lambda db_, key, **kw: sent.append((key, kw.get("entity_id"))) or [])
    run = [p for p in _pls(db, c.id).values() if p.status == "запущен"][:2]
    for p in run:
        p.fixed_plan = float(c.plan_show)                    # два ручных плана по плану РК — сумма вдвое больше
    db.flush()
    old = c.plan_show
    realloc.alert_plan_cut(db, {c.id: old})                  # план не менялся — превышение уже было, не шумим
    assert sent == []
    realloc.alert_plan_cut(db, {c.id: old * 3})              # был больше суммы ручных, стал меньше — сигнал
    assert sent == [("traffic_manual_over_plan", c.id)]
    v = _realloc_view(db, c)
    assert v["over_plan"] and v["over_plan"]["manual"] == round(2 * old)
    reset = {s["key"]: s for s in v["scenarios"]}["reset"]
    assert reset["enabled"] and reset["urgent"]
    assert all(p.fixed_plan == float(old) for p in run)      # сами планы на месте: убирает человек
