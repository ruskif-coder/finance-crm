# -*- coding: utf-8 -*-
"""Итоговая сверка сделки (app/final_recon/closing.py, владелец 15.10.2026): бонус одним из трёх, пин по умолчанию,
вывод с учётом бонуса, ручная сумма — только мастер/админ и не больше МП. Записи на стенд не остаются: всё в откатываемой транзакции."""
import pytest

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL


def test_bonus_three_ways():
    assert CL.bonus_shows("pct", 10, 2_000_000, 700_000) == pytest.approx(200_000)
    assert CL.bonus_shows("qty", 150_000, 2_000_000, 700_000) == 150_000
    # 80 000 ₽ по CPM плана 350 ₽ → ≈ 228 571 показ
    assert CL.bonus_shows("rub", 80_000, 2_000_000, 700_000) == pytest.approx(80_000 / 350 * 1000)
    assert CL.bonus_shows(None, None, 2_000_000, 700_000) == 0
    assert CL.bonus_shows("rub", 80_000, 0, 700_000) == 0          # без плана CPM не посчитать — бонус не выдумываем


def test_default_pin_follows_plan():
    assert CL.default_mode(1000, 1000) == "plan"
    assert CL.default_mode(1000, 1200) == "plan"
    assert CL.default_mode(1000, 999) == "fact"
    assert CL.default_mode(1000, None) == "fact"


@pytest.mark.parametrize("fact,bonus,code", [
    (960, 0, "under"), (970, 0, "in_plan"), (1030, 0, "in_plan"), (1040, 0, "over"),
    (1080, 100, "in_plan"), (1120, 100, "over"), (None, 0, "no_fact"),
])
def test_verdict_thresholds_97_103_and_bonus(fact, bonus, code):
    """97 % и 103 % — один порог для вывода и цвета факта; перекрут в пределах бонуса — не перекрут."""
    assert CL.verdict(1000, fact, bonus)["code"] == code


@pytest.fixture
def deal_db():
    """Сделка стенда с медиапланом; всё, что тест пишет, откатывается."""
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d JOIN sales_media_plans mp ON mp.deal_id = d.id
         JOIN sales_media_plan_rows r ON r.plan_id = mp.id
         WHERE mp.status <> 'rejected' AND r.unit_price > 0 AND r.volume > 0
         ORDER BY d.id LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет сделки с посчитанным МП")
    try:
        yield db, db.get(SalesDeal, row[0])
    finally:
        db.rollback()
        db.close()


class _U:
    id = None


def test_manual_only_for_privileged(deal_db):
    db, d = deal_db
    with pytest.raises(CL.ClosingError) as e:
        CL.set_mode(db, d, "manual", 1000, _U(), privileged=False)
    assert e.value.status == 403


def test_manual_not_above_mp(deal_db):
    db, d = deal_db
    mp = CL.compute(db, d)["base_plan_net"]
    with pytest.raises(CL.ClosingError) as e:
        CL.set_mode(db, d, "manual", mp + 1, _U(), privileged=True)
    assert e.value.status == 400
    out = CL.set_mode(db, d, "manual", mp / 2, _U(), privileged=True)
    assert out["mode"] == "manual" and out["base_ds_net"] == pytest.approx(round(mp / 2, 2), abs=0.01)


def test_plan_pin_is_mp_sum_and_extras_add(deal_db):
    db, d = deal_db
    out = CL.set_mode(db, d, "plan", None, _U(), privileged=False)
    assert out["base_ds_net"] == out["base_plan_net"]
    assert out["total_net"] == pytest.approx(out["base_plan_net"] + out["paid_extras_net"], abs=0.01)


def test_pin_row_does_not_hide_the_rule_sk(deal_db):
    """15.10.2026: строку сверки создаёт пин суммы ДС — пустой СК в ней не должен перекрывать СК условий. С 27.10.2026
    СК — правило «Агентских условий» по договору закрытия и агентству сделки."""
    from datetime import date
    from sqlalchemy import text
    from app.agency_terms import service as T
    from app.final_recon import sk as SK
    db, d = deal_db
    if not d.ord_final_contract_id:
        d.ord_final_contract_id = db.execute(text("SELECT id FROM contracts WHERE counterparty_id IS NOT NULL LIMIT 1")).scalar()
    if not (d.agency_id or d.advertiser_id):
        d.agency_id = db.execute(text("SELECT id FROM sales_agencies LIMIT 1")).scalar()
    db.flush()
    T.save_rule(db, {"kind": "основная", "contract_id": d.ord_final_contract_id, "agency_id": d.agency_id,
                     "advertiser_id": None if d.agency_id else d.advertiser_id, "brand_id": d.brand_id,
                     "service_id": d.service_id, "mode": "скидка в счёт", "percent": 10,
                     "valid_from": date(2000, 1, 1)}, _U())
    CL.set_mode(db, d, "plan", None, _U(), privileged=False)
    assert SK.of_deal(db, d)["source"] == "rule"
    out = CL.compute(db, d)
    assert out["sk"]["mode"] == "скидка в счёт"
    assert out["total_net"] == pytest.approx(out["sk"]["before_net"] - out["sk"]["amount_net"], abs=0.01)


def test_manual_volume_goes_to_ds(deal_db):
    """«Вручную»: единицы и сумма сохраняются вместе; единицы уходят в ДС, по факту — факт не больше плана."""
    db, d = deal_db
    mp = CL.compute(db, d)["base_plan_net"]
    out = CL.set_mode(db, d, "manual", mp / 2, _U(), privileged=True, manual_volume=12345)
    assert out["manual_volume"] == 12345 and out["ds_volume"] == 12345
    out = CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    assert out["ds_volume"] == (out["plan_shows"] or None)


# ── актуальность Adfox (долг 14.10, владелец 16.10) ─────────────────────────
from datetime import date as _d


@pytest.mark.parametrize("dates,end,yesterday,stale", [
    ({"dsp": _d(2026, 10, 10)}, _d(2026, 10, 31), _d(2026, 10, 15), False),                       # Adfox нет — нечего сверять
    ({"adfox": _d(2026, 10, 8), "dsp": _d(2026, 10, 10)}, _d(2026, 10, 31), _d(2026, 10, 15), True),  # Adfox отстал от DSP
    ({"adfox": _d(2026, 10, 10), "dsp": _d(2026, 10, 10)}, _d(2026, 10, 31), _d(2026, 10, 15), False),
    ({"adfox": _d(2026, 10, 20)}, _d(2026, 10, 25), _d(2026, 10, 27), True),                       # только Adfox, РК кончилась позже
    ({"adfox": _d(2026, 10, 25)}, _d(2026, 10, 25), _d(2026, 10, 27), False),
])
def test_adfox_freshness(dates, end, yesterday, stale):
    r = CL.adfox_freshness(dates, end, yesterday)
    assert (r is not None) == stale
    if r:
        assert r["adfox_as_of"] == dates["adfox"].isoformat()
