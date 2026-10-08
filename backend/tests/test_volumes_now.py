# -*- coding: utf-8 -*-
"""Пересчёт объёмов «сейчас» по событию (владелец 08.10.2026): согласованная площадка не ждёт ночи."""
import inspect
from datetime import date, timedelta

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.ad import build, volumes_now
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.database import SessionLocal


@pytest.fixture
def camp():
    """РК на 3 площадки, 11-й день флайта: две запущены, третья согласована и ждёт запуска (плана у неё нет)."""
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
    c = AdCampaign(deal_id=deal_id, status="запущена", plan_show=3000, ms_campaign_xxhash="TESTNOWCAMP00001",
                   date_start=today - timedelta(days=10), date_end=today + timedelta(days=20))
    db.add(c)
    db.flush()
    pls, crs = [], []
    for i, (pub, st) in enumerate(zip(pubs, ("запущен", "запущен", "ждёт запуска"))):
        p = AdCampaignPlacement(campaign_id=c.id, publisher_id=pub, weight=1, status=st)
        db.add(p)
        db.flush()
        pls.append(p)
        cr = AdCampaignCreative(campaign_id=c.id, placement_id=p.id, creative_no=1, status="согласован",
                                ms_creative_xxhash=f"TESTNOWCR00000{i}1" if i < 2 else None)
        db.add(cr)
        crs.append(cr)
    db.commit()
    build.recompute_shares(db, c.id, facts={}, facts_given=True)
    db.commit()
    run_from = db.execute(text("SELECT coalesce(max(id), 0) FROM bidder_run")).scalar()
    yield db, c, pls, crs
    db.rollback()
    db.execute(text("DELETE FROM bidder_run WHERE id > :r"), {"r": run_from})
    db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": c.id})
    db.commit()
    db.close()


class FakeMs:
    def __init__(self, fail=False):
        self.edits, self.fail = [], fail

    def last_sent_show_limit(self, ref):
        return None

    def creative_edit(self, xxhash, body, local_ref=None):
        if self.fail:
            from app.dsp.client import MsError
            raise MsError("DSP недоступен")
        self.edits.append((xxhash, body["limits"]["show"]["total"]))


def test_an_approved_site_gets_a_preview_volume_without_touching_anyones_plan(camp):
    db, c, pls, crs = camp
    before = {p.id: p.plan_show for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id)}
    assert not before[pls[2].id], "согласованная, но не запущенная площадка плана не имеет (правило 5-го дня)"
    got = volumes_now.preview_plans(db, c)
    assert set(got) == {crs[2].id}                       # только её креатив
    assert got[crs[2].id] == pytest.approx(1000, abs=2)  # делят три: 3000 / 3
    db.expire_all()
    after = {p.id: p.plan_show for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id)}
    assert after == before, "предварительный объём на лету: в базу не пишется, остальным не меняется"


def test_no_preview_in_the_hold_period_because_everyone_in_work_is_already_planned(camp):
    db, c, pls, crs = camp
    c.date_start = date.today() - timedelta(days=2)
    db.commit()
    build.recompute_shares(db, c.id, facts={}, facts_given=True)
    db.commit()
    assert pls[2].plan_show, "в удержание согласованная площадка уже в раскладке"
    assert volumes_now.preview_plans(db, c) == {}


def test_refresh_pushes_limits_to_dsp_at_once(camp, monkeypatch):
    db, c, pls, crs = camp
    ms = FakeMs()
    out = volumes_now.refresh_volumes_now(db, c.deal_id, client=ms)
    assert out["limits"]["failed"] == [] and ms.edits, "лимиты ушли в DSP сразу, не ночью"
    assert {x[0] for x in ms.edits} <= {"TESTNOWCR0000001", "TESTNOWCR0000011"}


def test_a_dsp_failure_is_reported_and_never_raises(camp):
    db, c, pls, crs = camp
    out = volumes_now.refresh_volumes_now(db, c.deal_id, client=FakeMs(fail=True))
    assert out["limits"]["failed"] and "campaign_id" in out


def test_no_campaign_is_a_quiet_skip():
    db = SessionLocal()
    try:
        free = db.execute(text("SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
                               "WHERE c.id IS NULL LIMIT 1")).scalar()
        if free:
            assert volumes_now.refresh_volumes_now(db, free) == {"skipped": "нет РК"}
    finally:
        db.close()


def test_the_events_call_the_function():
    from app.routers import launch_prep as lp
    from app.routers import traffic_dashboard as td
    v = inspect.getsource(lp.apply_platform_verdict)
    assert "refresh_volumes_now" in v and v.index("db.commit()") < v.index("refresh_volumes_now")
    assert "push_limits" in inspect.getsource(td.set_placement_status)
    assert "push_limits" in inspect.getsource(td.set_campaign_status)


def test_the_passport_has_the_preview_note_column():
    from app.traffic import offsite_export as OX
    assert OX.HEAD[-1] == "Пометка объёма" and len(OX.HEAD) == 21
