# -*- coding: utf-8 -*-
"""РК появляется по событию — когда сделка входит в стадии сборки, а не ночным прогоном (07.10.2026).

БЫЛО. `sync_campaigns` ходил по сделкам раз в сутки (06:05 UTC) и по кнопке «Обновить из сделок».
Сделку могли собрать за пару часов, а трафик увидел бы её в дашборде только утром (SA5JUK 07.10:
стадия «Готовятся к старту», а РК нет). ТЕПЕРЬ перевод сделки на стадию сборки или дальше
(`stage_move.apply_move` — единственное место, через которое идут диалог, массовая правка и автоматика)
заводит РК этой сделки сразу: кампания, площадки-кандидаты, креативы — тем же расчётом, что у ночного
прогона. Он остаётся страховкой на сделки, созданные сразу на стадии (минуя перевод).

Тесты пишут в транзакцию и откатывают её: на стенде ничего не остаётся.
"""
import logging

import pytest

import app.main  # noqa: F401 — реестр моделей: без него внешние ключи сделки не находят таблицы
from app.ad import build
from app.ad.models import AdCampaign
from app.database import SessionLocal
from app.sales import stage_move
from app.sales.models import SalesDeal, SalesStage


@pytest.fixture
def s():
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


def _deal_without_campaign(db):
    row = db.execute(build.text(
        "SELECT d.id FROM sales_deals d WHERE NOT EXISTS (SELECT 1 FROM ad_campaign c WHERE c.deal_id = d.id) "
        "AND d.period_from IS NOT NULL ORDER BY d.id DESC LIMIT 1")).first()
    if row is None:
        pytest.skip("на стенде нет сделки без РК")
    return db.get(SalesDeal, row[0])


def _stage(db, key):
    st = db.query(SalesStage).filter(SalesStage.stage_key == key).order_by(SalesStage.id).first()
    if st is None:
        pytest.skip(f"нет стадии {key}")
    return st


def _campaigns(db, deal_id):
    return db.query(AdCampaign).filter(AdCampaign.deal_id == deal_id).all()


def test_entering_the_assembly_stage_creates_the_campaign(s):
    deal = _deal_without_campaign(s)
    assert not _campaigns(s, deal.id)
    out = build.ensure_campaign_on_move(s, deal, _stage(s, build.ASSEMBLY_STAGE_KEY))
    camps = _campaigns(s, deal.id)
    assert len(camps) == 1 and out and out["created"], out
    assert camps[0].status == build.STATUS_WAITING
    assert camps[0].date_start == deal.period_from and camps[0].date_end == deal.period_to


def test_a_stage_before_assembly_does_not(s):
    deal = _deal_without_campaign(s)
    assert build.ensure_campaign_on_move(s, deal, _stage(s, "media_plan")) is None
    assert not _campaigns(s, deal.id)


def test_an_existing_campaign_is_left_alone(s):
    deal = _deal_without_campaign(s)
    target = _stage(s, build.ASSEMBLY_STAGE_KEY)
    build.ensure_campaign_on_move(s, deal, target)
    camp = _campaigns(s, deal.id)[0]
    camp.status = "запущена"                    # ею дальше управляет трафик
    s.flush()
    assert build.ensure_campaign_on_move(s, deal, target) is None
    assert _campaigns(s, deal.id)[0].status == "запущена"


def test_a_build_failure_does_not_break_the_move_and_leaves_nothing(s, monkeypatch, caplog):
    deal = _deal_without_campaign(s)
    monkeypatch.setattr(build, "sync_deal", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сборка упала")))
    with caplog.at_level(logging.WARNING, logger="finance.ad"):
        assert build.ensure_campaign_on_move(s, deal, _stage(s, build.ASSEMBLY_STAGE_KEY)) is None
    assert not _campaigns(s, deal.id), "частично собранная РК остаться не должна"
    assert any("не заведена" in r.message for r in caplog.records)


def test_apply_move_builds_the_campaign_in_the_same_transaction(s):
    """Через настоящий `apply_move`: перевод и РК — одно целое, откат отменяет оба."""
    deal = _deal_without_campaign(s)
    target = _stage(s, build.ASSEMBLY_STAGE_KEY)
    if deal.our_stage_id == target.id:
        pytest.skip("сделка уже на стадии сборки")
    res = stage_move.apply_move(s, deal, target, user=None, reason="тест: РК по событию")
    assert res["moved"] and len(_campaigns(s, deal.id)) == 1
    s.rollback()
    assert not _campaigns(s, deal.id)
