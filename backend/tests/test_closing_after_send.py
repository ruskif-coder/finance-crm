# -*- coding: utf-8 -*-
"""Сумма ДС после «Отправить в ДО» (владелец 22.10.2026, по аудиту 2.7.0 п. 2.2): «до 1С можно, но только мастеру и админу».
Пакет в «черновике» — можно; в «согласовании» ДС уже собраны из суммы — отказ с подсказкой вернуть пакет в раскладку;
с «ждём 1С» и дальше — закрыто всем. Записи на стенд не остаются: всё в откатываемой транзакции."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL


@pytest.fixture
def sent_deal(monkeypatch):
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
    d = db.get(SalesDeal, row[0])
    try:
        CL.set_mode(db, d, "plan", None, _U(), privileged=True)
        CL.freeze(db, d, _U())
        yield db, d
    finally:
        db.rollback()
        db.close()


class _U:
    id = None


def _package(monkeypatch, status):
    monkeypatch.setattr(CL, "package_status", lambda db, deal_id: status)


@pytest.mark.parametrize("status", [None, "черновик"])
def test_master_may_change_sum_before_1c(sent_deal, monkeypatch, status):
    db, d = sent_deal
    _package(monkeypatch, status)
    mp = CL.compute(db, d)["base_plan_net"]
    out = CL.set_mode(db, d, "manual", round(mp / 2, 2), _U(), privileged=True)
    assert out["frozen"] and out["base_ds_net"] == pytest.approx(round(mp / 2, 2))


def test_not_master_may_not_change_after_send(sent_deal, monkeypatch):
    db, d = sent_deal
    _package(monkeypatch, None)
    with pytest.raises(CL.ClosingError) as e:
        CL.set_mode(db, d, "fact", None, _U(), privileged=False)
    assert e.value.status == 403


def test_agreement_asks_to_return_package_to_layout(sent_deal, monkeypatch):
    db, d = sent_deal
    _package(monkeypatch, "согласование")
    with pytest.raises(CL.ClosingError) as e:
        CL.set_mode(db, d, "fact", None, _U(), privileged=True)
    assert e.value.status == 409 and "раскладку" in e.value.message


@pytest.mark.parametrize("status", ["ждём 1С", "выставление", "ждём оплату", "ждём сканы", "архив"])
def test_closed_for_everyone_from_1c_on(sent_deal, monkeypatch, status):
    db, d = sent_deal
    _package(monkeypatch, status)
    with pytest.raises(CL.ClosingError) as e:
        CL.set_mode(db, d, "fact", None, _U(), privileged=True)
    assert e.value.status == 409 and "1С" in e.value.message


def test_compute_tells_the_screen_whether_sum_is_editable(sent_deal, monkeypatch):
    db, d = sent_deal
    _package(monkeypatch, "черновик")
    assert CL.compute(db, d)["sum_open"] is True
    _package(monkeypatch, "ждём 1С")
    assert CL.compute(db, d)["sum_open"] is False


def test_package_status_reads_the_master_deal():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        row = db.execute(text("""SELECT i.deal_id, m.status FROM master_deal_items i
                                   JOIN master_deals m ON m.id = i.master_deal_id LIMIT 1""")).first()
        if not row:
            pytest.skip("на стенде нет мастер-сделок")
        assert CL.package_status(db, row[0]) == row[1]
    finally:
        db.close()
