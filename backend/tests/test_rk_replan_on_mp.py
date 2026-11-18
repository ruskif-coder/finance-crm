# -*- coding: utf-8 -*-
"""План РК следует за медиапланом сразу, а не утренним прогоном (владелец 18.11.2026).

Повод: аккаунт уменьшила объём в медиаплане четырёх запущенных РК (остаток ушёл в копию сделки), а РК трафика держали
старый план до 06:05 следующего дня, лимиты в DSP — ещё сутки: ночной пересчёт лимитов (02:00) шёл РАНЬШЕ подтяжки плана.

Поломки, которые ловит набор:
- `replan_deal` не переносит объём новой версии в план РК (или трогает РК сделки вне стадий сборки);
- сохранение медиаплана перестало звать пересчёт РК (любая из двух веток записи: правка версии и новая версия);
- ночной `daily_shares` снова считает доли и лимиты до подтяжки плана из медиаплана."""
import inspect

from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.ad import build, daily_shares
from app.ad.models import AdCampaign
from app.database import SessionLocal
from app.routers import media_plans
from app.sales.models import SalesDeal


def _camp_on_assembly(db):
    ids = [d["id"] for d in build._campaign_deals(db, build.assembly_stage_ids(db))]
    return db.query(AdCampaign).filter(AdCampaign.deal_id.in_(ids or [0])).order_by(AdCampaign.id).all()


def test_replan_takes_the_new_media_plan_volume():
    db = SessionLocal()
    try:
        camp = next((c for c in _camp_on_assembly(db) if (build.deal_plan(db, c.deal_id)["plan_show"] or 0) > 1000), None)
        assert camp is not None, "на стенде нет РК на стадии сборки с медиапланом"
        latest = db.execute(text(f"SELECT ({build.LATEST_PLAN_SQL})"), {"d": camp.deal_id}).scalar()
        db.execute(text("UPDATE sales_media_plan_rows SET volume = volume / 2 WHERE plan_id = :p"), {"p": latest})
        want = build.deal_plan(db, camp.deal_id)["plan_show"]
        camp.plan_show = want * 3          # РК держит старый, больший план
        db.flush()
        res = build.replan_deal(db, camp.deal_id, commit=False)
        assert res["changed"] is True
        assert round(camp.plan_show) == round(want)
        assert build.replan_deal(db, camp.deal_id, commit=False)["changed"] is False   # второй раз — нечего менять
    finally:
        db.rollback()
        db.close()


def test_replan_leaves_deals_outside_assembly_alone():
    db = SessionLocal()
    try:
        st = build.assembly_stage_ids(db)
        camp = (db.query(AdCampaign).join(SalesDeal, SalesDeal.id == AdCampaign.deal_id)
                .filter(~SalesDeal.our_stage_id.in_(st)).first())
        if camp is None:
            return
        camp.plan_show = 123.0
        db.flush()
        assert build.replan_deal(db, camp.deal_id, commit=False) is None
        assert camp.plan_show == 123.0
    finally:
        db.rollback()
        db.close()


def test_saving_a_media_plan_replans_its_campaign_in_both_write_paths():
    src = inspect.getsource(media_plans.save_media_plan)
    assert src.count("follow_plan_change(") == 2, "обе ветки записи (правка версии и новая версия) зовут пересчёт РК"
    from app.sales import mp_follow
    assert "replan_now(" in inspect.getsource(mp_follow.follow_plan_change)


def test_nightly_shares_pull_the_plan_before_weights_and_limits():
    src = inspect.getsource(daily_shares.run)
    assert "sync_campaigns(" in src
    assert src.index("sync_campaigns(") < src.index("refresh_weights("), "план из медиаплана — до долей и лимитов"
