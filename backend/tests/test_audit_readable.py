# -*- coding: utf-8 -*-
"""Журнал действий читается человеком (владелец, 24.09.2026).

«Жанна Смирнова · move_deal · МП Подготовка → МП Отправлено» — непонятно ни что за
событие, ни о какой сделке речь. Две правки:
  · у КАЖДОГО действия в коде есть русская подпись (`app/audit_labels.py`,
    прибор — `test_action_labels.py`, потолок 0);
  · у записи есть «объект»: для сделки — её код и название со ссылкой на карточку, для
    медиаплана, площадки, контрагента и прочих — имя. Считается при показе, поэтому
    подписаны и старые записи.
"""
def test_a_deal_entry_names_the_deal():
    from app.audit_objects import describe
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    try:
        d = db.query(SalesDeal).filter(SalesDeal.code.isnot(None)).order_by(SalesDeal.id).first()
        if d is None:
            import pytest
            pytest.skip("на стенде нет сделок")
        out = describe(db, [("sales_deal", d.id), ("sales_deal", 10 ** 9)])
        obj = out[("sales_deal", d.id)]
        assert d.code in obj["label"] and obj["href"] == f"/sales/deals/{d.code}"
        assert "удал" in out[("sales_deal", 10 ** 9)]["label"], "исчезнувшая сделка — словами"
    finally:
        db.close()


def test_the_journal_returns_the_object():
    import inspect
    from app.routers import users
    assert "describe(" in inspect.getsource(users.get_audit_log)
