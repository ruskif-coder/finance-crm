# -*- coding: utf-8 -*-
"""Боковая панель операции (владелец 09.11.2026, хендофф `docs/design_handoff_operation_panel.zip`, контракт — его sampleData.js):
операция моста знает пакет, ДС, сделки, документы 1С и договор; ручная — только деньги, стороны, историю; оплаты — по цепочке
траншей, история — новые сверху, оплаты в ней — «деньги». Ломается, если связь «операция → комплект → ДС → сделки» потеряется
или оплата начнёт считаться по одной строке. Транзакция откатывается."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app import operation_context as OC


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_bridge_operation_knows_its_package_annex_deals_and_1c_documents(db):
    from app.master_deal.models import MasterDeal, MasterDealUpd
    from app.models import Operation
    op = db.query(Operation).filter(Operation.master_deal_upd_id.isnot(None)).order_by(Operation.id).first()
    if op is None:
        pytest.skip("на стенде нет операций моста")
    k = db.get(MasterDealUpd, op.master_deal_upd_id)
    m = db.get(MasterDeal, k.master_deal_id)
    c = OC.build(db, op, can_download_docs=True)
    assert c["package"]["code"] == m.code and c["package"]["upd_no"] == k.upd_no
    assert c["ds"]["id"] == k.annex_id and c["ds"]["number"] and c["ds"]["amount"] == round(float(k.gross), 2)
    assert c["deals"], "сделки ДС — через разнесение"
    assert any(d["advertiser"] for d in c["deals"]), "рекламодатель сделки (владелец 09.11: «не хватает рекламодателя»)"
    assert all("agency" in d for d in c["deals"]), "агентство сделки — рядом с контрагентом, если есть"
    assert c["ds"]["external"] in (True, False) and "has_file" in c["ds"], "свой ДС — просмотр, внешний — файл или ЭДО"
    assert c["upd"]["inv_no"] == k.onec_invoice_no and c["upd"]["kit_id"] == k.id
    assert c["contract"]["id"] == m.contract_id
    assert c["kind"] == "plan_income" and c["direction"] == "in" and c["can_download_docs"] is True


def test_advertiser_name_is_full_legal_name_when_written(db):
    """Владелец 09.11: «рекламодателя тоже пиши полностью». Ломается, если вернуть короткое имя (short_name)."""
    from app.models import Operation
    op = db.query(Operation).filter(Operation.master_deal_upd_id.isnot(None)).order_by(Operation.id).first()
    if op is None:
        pytest.skip("на стенде нет операций моста")
    ad = OC.build(db, op)["deals"][0]["advertiser"]
    db.execute(text("UPDATE sales_advertisers SET short_name = 'Крат', legal_name = 'ООО «Полное Имя»' WHERE id = :i"), {"i": ad["id"]})
    assert OC.build(db, op)["deals"][0]["advertiser"]["name"] == "ООО «Полное Имя»"
    db.execute(text("UPDATE sales_advertisers SET legal_name = NULL, name = 'Полное без юрлица' WHERE id = :i"), {"i": ad["id"]})
    assert OC.build(db, op)["deals"][0]["advertiser"]["name"] == "Полное без юрлица"


def _op(db, **kw):
    row = {"status": "ПЛАН ПОСТУПЛЕНИЙ", "income": 0, "expense": 0, "period": "2026-10", "parent": None, "date": "2026-11-01", **kw}
    return db.execute(text("INSERT INTO operations (status, income, expense, period, parent_operation_id, date) "
                           "VALUES (:status, :income, :expense, :period, :parent, :date) RETURNING id"), row).scalar()


def test_manual_operation_has_no_origin_and_payments_come_from_its_chain(db):
    from app.models import Operation
    root = _op(db, income=1000)
    _op(db, status="ОПЛАЧЕНО", income=400, parent=root, date="2026-11-05")
    _op(db, status="ОПЛАЧЕНО", income=250, parent=root, date="2026-11-07")
    c = OC.build(db, db.get(Operation, root), can_download_docs=False)
    assert c["package"] is None and c["upd"] is None and c["ds"] is None and c["deals"] == []
    assert [p["amount"] for p in c["payments"]] == [400.0, 250.0]
    assert c["period_label"] == "октябрь 2026" and c["amount"] == 1000.0
    money = [h for h in c["history"] if h["kind"] == "money"]
    assert len(money) == 2 and "07.11.2026" in money[0]["text"] and "05.11.2026" in money[1]["text"], "история — новые сверху"


def test_manual_operation_keeps_its_hand_written_description_and_requisites(db):
    """Владелец 09.11: «для старых и вне контура не показываются текстовые описания, а там фиксировалась важная информация».
    Ломается, если описание и вписанные руками № ДС / счёт / ссылка выпадут из панели."""
    from app.models import Operation
    i = db.execute(text("INSERT INTO operations (status, income, expense, period, description, ds_num, invoice, invoice_date, document_link) "
                        "VALUES ('ПЛАН ОПЛАТ', 0, 1600000, 'Q2 2026', 'аванс по договору, вернуть при срыве', 'доп 18', '77', "
                        "'2026-05-01', 'https://example.org/doc') RETURNING id")).scalar()
    n = OC.build(db, db.get(Operation, i))["note"]
    assert n == {"description": "аванс по договору, вернуть при срыве", "ds_num": "доп 18", "invoice": "77",
                 "invoice_date": "2026-05-01", "document_link": "https://example.org/doc"}


def test_endpoint_answers_404_with_a_hint_for_a_missing_operation(db):
    from fastapi import HTTPException
    from app.routers.operations import operation_context
    with pytest.raises(HTTPException) as e:
        operation_context(10 ** 9, db=db, current_user=None)
    assert e.value.status_code == 404 and "Обновите" in e.value.detail
