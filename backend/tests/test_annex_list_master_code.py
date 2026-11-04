# -*- coding: utf-8 -*-
"""Реестр ДС показывает мастер-сделку рядом со сделками (владелец 04.11.2026).

Поломка, которую ловит: ДС пакета в реестре без кода своей мастер-сделки — по строке не понять, из какого пакета документ.
"""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import annexes as R


def test_annex_of_a_package_carries_its_master_code():
    db = SessionLocal()
    try:
        row = db.execute(text("""SELECT a.id, m.code FROM sales_annexes a JOIN master_deals m ON m.id = a.master_deal_id
                                  ORDER BY a.id DESC LIMIT 1""")).first()
        if row is None:
            pytest.skip("на стенде нет ДС мастер-сделки")
        admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        items = {i["id"]: i for i in R.list_annexes(db=db, user=admin)["items"]}
        assert items[row.id]["master_code"] == row.code
        assert all("master_code" in i for i in items.values())
    finally:
        db.rollback()
        db.close()
