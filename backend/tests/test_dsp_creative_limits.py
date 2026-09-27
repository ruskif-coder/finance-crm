"""Лимит креатива в DSP — его доля, и он догоняет план (владелец 27.09.2026).

До 27.09 при выгрузке каждый креатив получал лимитом ВЕСЬ план площадки (три креатива —
трижды её объём), а до запуска площадки объёма не было вовсе, и креатив уезжал без
лимита. Теперь лимит — доля креатива (`build.creative_plans`, то же правило, что в
раскрытии дашборда), а ночной прогон подтягивает лимиты уже заведённых креативов.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.ad import build
from app.database import SessionLocal


@pytest.fixture()
def camp():
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    db = SessionLocal()
    deal_id = db.execute(text(
        "SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
        "WHERE c.id IS NULL ORDER BY d.id LIMIT 1")).scalar()
    pub = db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 1")).scalar()
    if not (deal_id and pub):
        pytest.skip("нет свободной сделки или площадки")
    c = AdCampaign(deal_id=deal_id, status="запущена", plan_show=900,
                   date_start=date.today(), date_end=date.today() + timedelta(days=20),
                   ms_campaign_xxhash="TESTCAMP00000001")
    db.add(c)
    db.flush()
    pl = AdCampaignPlacement(campaign_id=c.id, publisher_id=pub, weight=1,
                             status="ждёт запуска", plan_show=900)
    db.add(pl)
    db.flush()
    crs = []
    for no, st, xx in ((1, "согласован", "TESTCR0000000001"), (2, "у площадки", None),
                       (3, "отклонён", "TESTCR0000000003")):
        cr = AdCampaignCreative(campaign_id=c.id, placement_id=pl.id, creative_no=no,
                                status=st, ms_creative_xxhash=xx)
        db.add(cr)
        crs.append(cr)
    db.commit()
    yield db, c, pl, crs
    db.rollback()
    db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": c.id})
    db.commit()
    db.close()


def test_creative_gets_its_share_not_the_whole_placement(camp):
    db, c, pl, crs = camp
    plans = build.creative_plans(db, c)
    assert plans == {crs[0].id: 450, crs[1].id: 450, crs[2].id: None}


def test_provision_sends_the_creatives_share():
    import inspect
    from app.dsp import provision
    src = inspect.getsource(provision._provision)
    assert "creative_plans(" in src
    assert 'r["placement"].plan_show' not in src, "лимитом снова уходит план площадки"


class FakeMs:
    def __init__(self, sent):
        self.sent = sent            # {local_ref: последний отправленный лимит}
        self.edits = []

    def last_sent_show_limit(self, local_ref):
        return self.sent.get(local_ref)

    def creative_edit(self, xxhash, params, local_ref=None):
        self.edits.append((xxhash, params, local_ref))
        return True


def test_limits_catch_up_only_where_they_changed(camp):
    from app.dsp.limits import sync_limits
    db, c, pl, crs = camp
    ms = FakeMs({f"cr{crs[0].id}": 900})
    out = sync_limits(db, c, ms)
    assert ms.edits == [("TESTCR0000000001", {"limits": {"show": {"total": 450}}},
                         f"cr{crs[0].id}")]
    assert out["updated"] == 1
    # отклонённый (лимита нет) и незаведённый (хеша нет) не трогаем
    ms2 = FakeMs({f"cr{crs[0].id}": 450})
    sync_limits(db, c, ms2)
    assert ms2.edits == [], "повторный прогон шлёт то, что уже стоит"


def test_one_failed_creative_does_not_stop_the_rest(camp):
    from app.dsp.client import MsError
    from app.dsp.limits import sync_limits
    db, c, pl, crs = camp

    class Boom(FakeMs):
        def creative_edit(self, *a, **k):
            raise MsError("DSP недоступен")
    out = sync_limits(db, c, Boom({}))
    assert out["failed"] and out["updated"] == 0


def test_nightly_run_rebuilds_shares_and_limits(camp, monkeypatch):
    from app.ad import daily_shares
    db, c, pl, crs = camp
    monkeypatch.setattr(build, "deal_plan", lambda db_, d: {"surfaces": ["web"], "services": []})
    monkeypatch.setattr(build, "publisher_weights", lambda db_, surf: {pl.publisher_id: 1.0})
    ms = FakeMs({})
    out = daily_shares.run(client=ms, campaign_ids=[c.id])
    assert out["shares"]["campaigns"] >= 1
    assert any(e[0] == "TESTCR0000000001" for e in ms.edits), "лимит не подтянут"
    assert out["failed"] == 0
    assert "лимитов в DSP обновлено" in daily_shares._report(out)


# ── ревью 27.09.2026 ─────────────────────────────────────────────────────────────

def test_after_hold_approved_creative_keeps_its_share(camp):
    """«Запущен» у креатива ставится только руками — запуск площадки его не переключает.
    С шестого дня согласованный креатив запущенной площадки обязан держать долю, иначе
    в DSP он уходит без лимита."""
    db, c, pl, crs = camp
    c.date_start = date.today() - timedelta(days=10)
    pl.status = "запущен"
    db.flush()
    plans = build.creative_plans(db, c)
    assert plans[crs[0].id] == 900, "согласованный креатив запущенной площадки без доли"
    assert plans[crs[1].id] is None, "«у площадки» после удержания долю не держит"
    assert plans[crs[2].id] is None


def test_zero_share_is_reported_not_sent(camp, monkeypatch):
    """Ноль в DSP — «без лимита». Нулевая доля не отправляется, а попадает в отчёт."""
    from app.dsp import limits
    db, c, pl, crs = camp
    monkeypatch.setattr(limits, "creative_plans", lambda db_, camp_: {crs[0].id: 0})
    ms = FakeMs({})
    out = limits.sync_limits(db, c, ms)
    assert ms.edits == []
    assert out["zero"] == [crs[0].id]


def test_provision_refuses_zero_share():
    import inspect
    from app.dsp import provision
    src = inspect.getsource(provision._provision)
    assert "plans.get(cre.id) == 0" in src and "нулевой объём" in src


def test_nightly_survives_a_non_dsp_error(camp, monkeypatch):
    """Любая ошибка одной РК — в отчёт, прогон идёт дальше и кончается кодом сбоя."""
    from app.ad import daily_shares
    from app.dsp import limits
    db, c, pl, crs = camp
    monkeypatch.setattr(build, "deal_plan", lambda db_, d: {"surfaces": ["web"], "services": []})
    monkeypatch.setattr(build, "publisher_weights", lambda db_, surf: {pl.publisher_id: 1.0})

    def boom(*a, **k):
        raise RuntimeError("база отвалилась")
    monkeypatch.setattr(limits, "sync_limits", boom)
    out = daily_shares.run(client=FakeMs({}), campaign_ids=[c.id])
    assert out["failed"] == 1
