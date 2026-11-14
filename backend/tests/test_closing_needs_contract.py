# -*- coding: utf-8 -*-
"""Подтверждение сверки без доходного договора (владелец 14.11.2026): у основной воронки (полный цикл) — нельзя, кроме прямого
рекламодателя (галочка в блоке ОРД); у контура аккаунта и приоритезации не запирает. Поломка: сверку подтверждают без договора —
ДС и закрывающие собираются без договора закрытия. Записи на стенд не остаются: всё в откатываемой транзакции."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL
from app.final_recon import flow as FLOW
from app.ord import matching as M


class _U:
    id = None
    role = "admin"


@pytest.fixture
def deal_db():
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d JOIN sales_media_plans mp ON mp.deal_id = d.id
          LEFT JOIN final_recon_deals f ON f.deal_id = d.id
         WHERE mp.version = (SELECT max(version) FROM sales_media_plans x WHERE x.deal_id = d.id) AND f.sent_at IS NULL
           AND EXISTS (SELECT 1 FROM sales_media_plan_rows r WHERE r.plan_id = mp.id AND r.unit_price > 0 AND r.volume > 0)
         ORDER BY d.id LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет неотправленной сделки с посчитанным МП")
    d = db.get(SalesDeal, row[0])
    d.ord_final_contract_id = None
    d.ord_direct_advertiser = False
    try:
        yield db, d
    finally:
        db.rollback()
        db.close()


def _no_resolved(monkeypatch):
    monkeypatch.setattr(M, "resolve_final", lambda db, deal: SimpleNamespace(contract=None))


def test_full_cycle_without_contract_cannot_be_confirmed(deal_db, monkeypatch):
    db, d = deal_db
    _no_resolved(monkeypatch)
    monkeypatch.setattr(FLOW, "of_deal", lambda db, deal: FLOW.FULL)
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    with pytest.raises(CL.ClosingError) as e:
        CL.confirm(db, d, True, _U())
    assert e.value.status == 409 and "доходный договор" in str(e.value)


def test_direct_advertiser_confirms_without_contract(deal_db, monkeypatch):
    db, d = deal_db
    _no_resolved(monkeypatch)
    monkeypatch.setattr(FLOW, "of_deal", lambda db, deal: FLOW.FULL)
    d.ord_direct_advertiser = True
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    assert CL.confirm(db, d, True, _U())["confirmed"]


def test_account_contour_is_not_blocked_by_contract(deal_db, monkeypatch):
    db, d = deal_db
    _no_resolved(monkeypatch)
    monkeypatch.setattr(FLOW, "of_deal", lambda db, deal: FLOW.ACCOUNT)
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    assert CL.confirm(db, d, True, _U())["confirmed"]


def test_compute_tells_the_screen_contract_is_missing(deal_db, monkeypatch):
    """Экран гасит кнопку заранее — флагом из расчёта, тем же правилом, что запрет при подтверждении."""
    db, d = deal_db
    _no_resolved(monkeypatch)
    monkeypatch.setattr(FLOW, "of_deal", lambda db, deal: FLOW.FULL)
    assert CL.compute(db, d)["contract_missing"] is True
    d.ord_direct_advertiser = True
    assert CL.compute(db, d)["contract_missing"] is False


def test_resolved_contract_is_saved_on_confirm_and_shown(deal_db, monkeypatch):
    """Договор найден сам (единственный договор плательщика с отметкой ОРД) — его засчитывают стадия и блок ОРД, а пакет ДС собирается
    только по сохранённому в сделке. Поломка: сверка подтверждена, «закрытие на: не выбран», «Отправить в ДО» отказывает."""
    from app.models import Contract
    db, d = deal_db
    c = db.query(Contract).filter(Contract.counterparty_id.isnot(None)).order_by(Contract.id).first()
    if c is None:
        pytest.skip("на стенде нет договора с контрагентом")
    monkeypatch.setattr(M, "resolve_final", lambda db, deal: SimpleNamespace(contract=c))
    monkeypatch.setattr(FLOW, "of_deal", lambda db, deal: FLOW.FULL)
    assert CL.compute(db, d)["closing_to"] is not None
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    CL.confirm(db, d, True, _U())
    assert d.ord_final_contract_id == c.id


def test_cost_and_report_open_without_mp_rows():
    """Поломка (14.11.2026): у сделки контура аккаунта без строк МП пропадал весь блок «Факт вводит аккаунт» — вместе с ним отчёт
    платформы и себестоимость, хотя от строк МП они не зависят. Без строк закрыт только сам факт."""
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    try:
        from app.final_recon import flow as F
        ids = db.execute(text("""
            SELECT d.id FROM sales_deals d
             WHERE NOT EXISTS (SELECT 1 FROM sales_media_plans mp JOIN sales_media_plan_rows r ON r.plan_id = mp.id WHERE mp.deal_id = d.id)
               AND NOT EXISTS (SELECT 1 FROM ad_campaign a WHERE a.deal_id = d.id)
               AND NOT EXISTS (SELECT 1 FROM final_recon_deals f WHERE f.deal_id = d.id AND f.sent_at IS NOT NULL)
             ORDER BY d.id DESC LIMIT 300""")).scalars().all()
        # Блок «Факт вводит аккаунт» — только у контура аккаунта: «последняя сделка» без этого фильтра попадала на еФарм
        # (полный цикл, блок закрыт законно) и тест краснел от демо-данных стенда (14.11.2026).
        did = next((i for i in ids if F.of_deal(db, db.get(SalesDeal, i)) == F.ACCOUNT), None)
        if did is None:
            pytest.skip("на стенде нет сделки контура аккаунта без строк МП и без РК")
        fe = CL.compute(db, db.get(SalesDeal, did))["fact_entry"]
        assert fe["can_enter"] is False and fe["open"] is True
    finally:
        db.rollback()
        db.close()
