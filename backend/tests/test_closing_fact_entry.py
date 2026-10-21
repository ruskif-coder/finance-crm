# -*- coding: utf-8 -*-
"""Ввод факта аккаунтом для услуг без РК (владелец 19.10.2026: Альфарм-Таргет, Polza, OLV).

Факт вводится по каждой базовой строке МП; дальше блок считает как у еФарма. Сделки со стенда, транзакция откатывается."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL


class _U:
    id = None
    name = "тест"


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _deal_without_rk(db):
    """Сделка услуги контура аккаунта с базовой CPM-строкой МП и без РК."""
    from app.sales.models import SalesDeal
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d
          JOIN sales_services s ON s.id = d.service_id
          JOIN sales_pipelines p ON p.id = s.realization_pipeline_id AND p.closing_flow = 'контур аккаунта'
          JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
          JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.volume > 0 AND upper(r.model) = 'CPM'
         WHERE NOT EXISTS (SELECT 1 FROM final_recon_deals f WHERE f.deal_id = d.id AND f.sent_at IS NOT NULL)
         ORDER BY d.id LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет сделки контура аккаунта с CPM-строкой и без РК")
    return db.get(SalesDeal, row[0])


def _deal_with_rk(db):
    """Сделка полного цикла (еФарм) — факт из статистики."""
    from app.sales.models import SalesDeal
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id
          JOIN sales_pipelines p ON p.id = s.realization_pipeline_id AND p.closing_flow = 'полный цикл'
          JOIN ad_campaign c ON c.deal_id = d.id ORDER BY d.id LIMIT 1""")).first()
    return db.get(SalesDeal, row[0])


def test_account_deal_with_empty_rk_still_takes_entered_fact(db):
    """Стадии заводят пустую РК и сделкам контура аккаунта — ввод факта от этого не закрывается."""
    from app.sales.models import SalesDeal
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id
          JOIN sales_pipelines p ON p.id = s.realization_pipeline_id AND p.closing_flow = 'контур аккаунта'
          JOIN ad_campaign c ON c.deal_id = d.id
          JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
          JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.volume > 0
         WHERE NOT EXISTS (SELECT 1 FROM final_recon_deals f WHERE f.deal_id = d.id AND f.sent_at IS NOT NULL)
         ORDER BY d.id LIMIT 1""")).first()
    if not row:
        pytest.skip("нет сделки контура аккаунта с РК и МП")
    d = db.get(SalesDeal, row[0])
    st = CL.compute(db, d)
    assert st["fact_entry"]["can_enter"], "пустая РК закрыла ввод факта"


def test_entered_fact_drives_the_block(db):
    d = _deal_without_rk(db)
    before = CL.compute(db, d)
    assert before["fact_shows"] is None and before["fact_entry"]["can_enter"]
    rows = before["fact_entry"]["rows"]
    plan = sum(r["volume"] for r in rows)
    CL.save_fact(db, d, {r["row_id"]: r["volume"] * 0.9 for r in rows}, "отчёт партнёра", _U())
    after = CL.compute(db, d)
    assert after["fact_shows"] == round(plan * 0.9)
    assert after["fact_source"] == "entered"
    assert after["verdict"]["code"] != "no_fact"
    assert after["amounts"]["fact"] == pytest.approx(after["base_plan_net"] * 0.9, abs=0.05)
    assert after["fact_entry"]["note"] == "отчёт партнёра"


def test_partial_entry_is_not_a_fact(db):
    d = _deal_without_rk(db)
    rows = CL.compute(db, d)["fact_entry"]["rows"]
    if len(rows) < 2:
        pytest.skip("у сделки одна базовая строка")
    CL.save_fact(db, d, {rows[0]["row_id"]: 100}, None, _U())
    assert CL.compute(db, d)["fact_shows"] is None, "факт не по всем строкам — это не факт сделки"


@pytest.mark.parametrize("bad", [{-1: 10}, "neg"])
def test_refusals(db, bad):
    d = _deal_without_rk(db)
    rows = CL.compute(db, d)["fact_entry"]["rows"]
    entries = {rows[0]["row_id"]: -5} if bad == "neg" else bad
    with pytest.raises(CL.ClosingError) as e:
        CL.save_fact(db, d, entries, None, _U())
    assert e.value.status == 400


def test_full_cycle_deal_takes_fact_from_stats(db):
    d = _deal_with_rk(db)
    assert CL.compute(db, d)["fact_entry"]["can_enter"] is False
    with pytest.raises(CL.ClosingError) as e:
        CL.save_fact(db, d, {1: 1}, None, _U())
    assert e.value.status == 409


# ── схема приёмки по модели строки (макет 14.10, владелец 19.10) ─────────────
@pytest.mark.parametrize("row,kind", [
    ({"model": "CPM", "format": "Баннеры"}, "cpm"),
    ({"model": "CPM", "format": "OLV In-stream"}, "video"),
    ({"model": "CPM", "position": "OLV", "format": None}, "video"),
    ({"model": "Fix"}, "fix"),
    ({"model": "ФИКС"}, "fix"),
    ({"model": "Пакет"}, "fix"),
    ({"model": "CPC"}, "cpc"),
])
def test_row_kind(row, kind):
    assert CL.row_kind(row) == kind


def test_metrics_and_vtr(db):
    d = _deal_without_rk(db)
    rows = CL.compute(db, d)["fact_entry"]["rows"]
    CL.save_fact(db, d, {r["row_id"]: {"fact": 1000, "clicks": 12, "completed": 700, "reference_shows": None} for r in rows}, None, _U())
    got = CL.compute(db, d)["fact_entry"]["rows"][0]
    assert got["clicks"] == 12
    if got["kind"] == "video":
        assert got["completed"] == 700 and got["vtr"] == 70.0


def test_cost_net(db):
    d = _deal_without_rk(db)
    st = CL.save_cost(db, d, 123456.78, _U())
    assert st["cost_net"] == 123456.78
    with pytest.raises(CL.ClosingError):
        CL.save_cost(db, d, -1, _U())
    assert CL.save_cost(db, d, None, _U())["cost_net"] is None


def test_report_flag_present(db):
    d = _deal_without_rk(db)
    assert "report" in CL.compute(db, d)["fact_entry"]


def test_sk_falls_back_to_income_contract_counterparty(db):
    """Плательщик не задан, доходный договор выбран — СК берётся у контрагента договора (19.10)."""
    from app.final_recon import sk as SK
    from app.sales.models import SalesDeal
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d JOIN contracts c ON c.id = d.ord_final_contract_id
         WHERE c.counterparty_id IS NOT NULL ORDER BY d.id LIMIT 1""")).first()
    if not row:
        pytest.skip("нет сделки с доходным договором")
    d = db.get(SalesDeal, row[0])
    want = db.execute(text("SELECT counterparty_id FROM contracts WHERE id = :c"), {"c": d.ord_final_contract_id}).scalar()
    d.payer_counterparty_id = None
    assert SK.payer_of(db, d).id == want
