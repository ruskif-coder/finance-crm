# -*- coding: utf-8 -*-
"""«Подтвердить ДС пакета» — одна транзакция (владелец 21.10.2026): отказ на любом ДС откатывает и уже подтверждённые."""
import pytest
from fastapi import HTTPException

from app.routers import annexes as AX


def test_failure_mid_package_rolls_back_everything(db, monkeypatch):
    from app.master_deal.models import MasterDeal
    from app.models import User
    from app.routers import master_deals as R
    from app.sales.models import SalesAnnex
    m = (db.query(MasterDeal).join(SalesAnnex, SalesAnnex.master_deal_id == MasterDeal.id)
         .filter(MasterDeal.status == "согласование", SalesAnnex.no.is_(None)).first())
    if m is None:
        pytest.skip("на стенде нет пакета на согласовании")
    user = db.query(User).filter(User.is_active == 1).filter(User.role.has(key="admin")).first()
    seen = []

    def half(db_, a, payload, user_):            # первый ДС «подтверждается», на втором вызове — отказ
        a.no, a.status = 999999, "подтверждён"
        seen.append(a.id)
        db_.flush()
        if len(seen) >= 1:
            raise HTTPException(409, "отказ проверки посреди пакета")
    monkeypatch.setattr(AX, "confirm_one", half)
    code, status = m.code, m.status
    with pytest.raises(HTTPException):
        R.master_confirm_ds(code, db, user)
    db.expire_all()
    assert db.query(SalesAnnex).filter(SalesAnnex.id.in_(seen), SalesAnnex.no.isnot(None)).count() == 0
    assert db.query(MasterDeal).filter_by(code=code).one().status == status
