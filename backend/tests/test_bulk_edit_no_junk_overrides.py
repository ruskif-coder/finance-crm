# -*- coding: utf-8 -*-
"""Массовая правка не пишет служебные поля как ручные правки сделки (аудит 23.09.2026, 3.M8).

Причина обхода требований (`override_reason`) — это слово к ДЕЙСТВИЮ, а не поле сделки.
Но она оставалась в наборе изменённых полей, и на КАЖДУЮ выбранную сделку ложилась
пометка «поле override_reason задано вручную». То же с пустой стадией (`our_stage_id:
null`). Пометки защищают поле от синхронизации, и мусорная пометка — это поле, которое
сверка потом «не трогает», хотя такого поля у сделки нет.

Вторая половина находки — массовый перевод в стадию реализации без воронки — НЕ
исправляется: реестр сознательно пропускает то, что нельзя (решение владельца
24.09.2026, временно, до разбора старых сделок; `test_stage_move_obeys_rules`).

Правка на живой сделке стенда ставит ту же услугу, что у неё уже есть, — данные не
меняются; пометки и запись журнала, созданные тестом, снимаются.
"""
from datetime import datetime

import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.models import User
from app.routers import sales_dashboard as sd
from app.sales.models import SalesDeal, SalesDealFieldOverride


def test_the_override_reason_is_not_an_override_of_the_deal():
    db = SessionLocal()
    started = datetime.utcnow()
    deal, before = None, set()
    try:
        deal = (db.query(SalesDeal).filter(SalesDeal.product.isnot(None))
                .order_by(SalesDeal.id).first())
        if deal is None:
            pytest.skip("на стенде нет сделки с услугой")
        before = {o.id for o in db.query(SalesDealFieldOverride)
                  .filter(SalesDealFieldOverride.deal_id == deal.id).all()}
        admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        sd.bulk_update_deals(sd.BulkUpdate(deal_ids=[deal.id], product=deal.product,
                                           our_stage_id=None,
                                           override_reason="разбор старых сделок"),
                             db, admin)
        new = [o for o in db.query(SalesDealFieldOverride)
               .filter(SalesDealFieldOverride.deal_id == deal.id).all()
               if o.id not in before]
        fields = {o.field_name for o in new}
        assert "override_reason" not in fields, "служебная причина записана полем сделки"
        assert "our_stage_id" not in fields, "пустая стадия записана ручной правкой"
    finally:
        db.rollback()
        if deal is None:
            db.close()
            return
        # Только СОЗДАННЫЕ тестом: пометку, существовавшую до него, не трогаем.
        db.execute(text("DELETE FROM sales_deal_field_overrides WHERE deal_id = :d "
                        "AND NOT (id = ANY(:keep))"), {"d": deal.id, "keep": list(before)})
        db.execute(text("DELETE FROM audit_log WHERE action = 'bulk_update_deals' "
                        "AND created_at >= :t"), {"t": started})
        db.commit()
        db.close()
