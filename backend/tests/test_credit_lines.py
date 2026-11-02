# -*- coding: utf-8 -*-
"""Кредитные линии в «Настройки → Остатки» (02.11.2026). Поломки: неизвестный банк или «выбрано» больше лимита
записываются молча; правка не попадает в журнал; выключенная линия продолжает считаться в сводке плана оплат."""

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import AuditLog, CreditLine
from app import pay_plan_summary as pps
from app.routers import settings as st


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.close()


def _admin(db):
    from app.models import User
    return db.query(User).join(User.role).filter_by(key="admin").first()


def test_bad_input_is_refused(db):
    user = _admin(db)
    with pytest.raises(HTTPException):
        st.create_credit_line(st.CreditLineIn(bank="Наличные", limit_amount=10), db=db, current_user=user)
    with pytest.raises(HTTPException):
        st.create_credit_line(st.CreditLineIn(bank="АльфаБанк", limit_amount=10, used_amount=11),
                              db=db, current_user=user)


def test_create_edit_switch_off_and_journal(db):
    user = _admin(db)
    before = len(pps._credit_lines(db))
    made = st.create_credit_line(st.CreditLineIn(bank="АльфаБанк", limit_amount=1000, used_amount=300,
                                                 note="прибор"), db=db, current_user=user)
    try:
        assert len(pps._credit_lines(db)) == before + 1
        st.update_credit_line(made["id"], st.CreditLineIn(bank="АльфаБанк", limit_amount=1000, used_amount=300,
                                                          note="прибор", is_active=False), db=db, current_user=user)
        assert len(pps._credit_lines(db)) == before, "выключенная линия считается"
        acts = {a for (a,) in db.query(AuditLog.action).filter(AuditLog.entity_type == "credit_line",
                                                               AuditLog.entity_id == made["id"])}
        assert {"credit_line_create", "credit_line_update"} <= acts
    finally:
        db.query(AuditLog).filter(AuditLog.entity_type == "credit_line", AuditLog.entity_id == made["id"]).delete()
        db.query(CreditLine).filter(CreditLine.id == made["id"]).delete()
        db.commit()
