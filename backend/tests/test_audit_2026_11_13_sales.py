# -*- coding: utf-8 -*-
"""Аудит 13.11.2026 — продажи (владелец 14.11: «пакет дёшево — да»)."""
import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401


def test_deal_from_plan_locks_the_plan_row():
    """Сломать: читать план без `with_for_update` — двойной клик «Создать сделку» даёт две сделки на один план.
    Гонку двух запросов в тесте не воспроизвести; пин — на замок строки ДО проверки «у плана уже есть сделка»."""
    from app.routers import media_plans
    src = inspect.getsource(media_plans.create_deal_from_plan)
    assert "with_for_update()" in src
    assert src.index("with_for_update()") < src.index("if p.deal_id:")


def test_service_used_by_deals_is_refused_with_400_not_500():
    """Сломать: убрать проверку сделок — удаление упрётся во внешний ключ `sales_deals.service_id` и ответит 500."""
    from app.database import SessionLocal
    from app.models import User
    from app.routers import sales_directories as R
    db = SessionLocal()
    try:
        sid = db.execute(text("""SELECT d.service_id FROM sales_deals d WHERE d.service_id IS NOT NULL
                                    AND NOT EXISTS (SELECT 1 FROM sales_annex_items i WHERE i.service_id = d.service_id)
                                  LIMIT 1""")).scalar()
        if sid is None:
            pytest.skip("на стенде нет сделки с услугой")
        user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
        db.commit = db.flush
        with pytest.raises(HTTPException) as e:
            R.delete_service_hard(sid, db=db, current_user=user)
        assert e.value.status_code == 400 and "сдел" in e.value.detail
    finally:
        db.rollback()
        db.close()
