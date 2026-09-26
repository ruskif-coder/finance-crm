"""Полоса «Сделки в работе» показывает успешный архив отдельной отметкой (владелец 26.09.2026).

Фильтр «скрыть архив» (включён по умолчанию) прятал из сводки «Архив успешных сделок», а
«Доведено до результата» их считает. У сейлза за Q3 это дало 8,79 против 8,64 млн — одна
сделка на 150 000 ₽, и две правдивые цифры рядом читались как ошибка суммирования.
Сводка теперь отдаёт скрытый успешный архив (`archived`), и факт сходится:
факт без фильтра = факт с фильтром + архив.
"""
import pytest

from app.database import SessionLocal
from app.models import User
from app.routers import sales_dashboard as sd
from app.sales.models import SalesDeal, SalesStage


def _call(db, user, rep, hide):
    return sd.dashboard(sales_rep_id=[rep], hide_archive=hide, db=db, current_user=user,
                        date_from=None, date_to=None, pipeline=None, bitrix_stage=None,
                        our_stage_id=None, account_manager_id=None, advertiser_id=None,
                        money_layer=None, brand_id=None, agency_id=None, product=None,
                        stage_key=None, search=None, gaps=None)


def _layer(out, name):
    b = next((x for x in out["by_layer"] if x["name"] == name), None)
    return (round(b["amount"]), b["deals"]) if b else (0, 0)


def test_hidden_successful_archive_is_reported_and_fact_reconciles():
    db = SessionLocal()
    try:
        rep = (db.query(SalesDeal.sales_rep_id)
               .join(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
               .filter(SalesStage.stage_key == 'archive', SalesDeal.sales_rep_id.isnot(None))
               .first())
        admin = db.query(User).join(User.role).filter_by(key='admin').first()
        if rep is None or admin is None:
            pytest.skip('нет сделки в успешном архиве или администратора')
        full = _call(db, admin, rep[0], False)
        hid = _call(db, admin, rep[0], True)
        arch = hid["archived"]
        assert arch["deals"] >= 1
        fa, fd = _layer(full, 'фактические')
        ha, hd = _layer(hid, 'фактические')
        assert fd == hd + arch["deals"]
        assert abs(fa - (ha + round(arch["amount"]))) <= 1
        # без фильтра архив уже внутри слоёв — отдельно не повторяется
        assert full["archived"] == {"amount": 0, "deals": 0}
    finally:
        db.close()
