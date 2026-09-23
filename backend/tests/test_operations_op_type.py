# -*- coding: utf-8 -*-
"""Прибор: «Тип операции» фильтрует на сервере (аудит 23.09.2026, 6.M3).

Раньше фильтр резал только загруженную страницу: при «Поступлениях» счётчик и
постраничность считались по всем операциям, а выгрузка отдавала и расходы.
"""
import app.notify.models  # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import operations as ops


def test_op_type_filters_rows_and_total():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
        base = dict(skip=0, limit=500, status=None, bank=None, article_id=None,
                    counterparty_id=None, period=None, gaps=None, ids=None, db=db,
                    current_user=admin)
        every = ops.get_operations(op_type=None, **base)["total"]
        inc = ops.get_operations(op_type=["income"], **base)
        exp = ops.get_operations(op_type=["expense"], **base)
        assert all(r["income"] > 0 for r in inc["items"])
        assert all(r["expense"] > 0 for r in exp["items"])
        assert 0 < inc["total"] < every and 0 < exp["total"] < every
        both = ops.get_operations(op_type=["income", "expense"], **base)["total"]
        assert both == inc["total"] + exp["total"]
    finally:
        db.close()
