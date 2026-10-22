# -*- coding: utf-8 -*-
"""Суммы сверки — деньги, а не двоичная дробь (внешний аудит 2.7.0, п. 2.1): модель объявляет тот же тип, что база
(`numeric(14,2)`, миграция 2026-10-15_closing_contour.sql). С `Float` ORM отдавал `float` до любого сложения."""
import pytest
from sqlalchemy import Numeric, text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.final_recon.models import FinalReconDeal


@pytest.mark.parametrize("col", ["ds_manual_net", "base_net", "cost_net"])
def test_model_and_database_agree_on_money_type(col):
    t = FinalReconDeal.__table__.c[col].type
    assert type(t) is Numeric and (t.precision, t.scale) == (14, 2), col      # Float — подкласс Numeric, поэтому type, а не isinstance
    db = SessionLocal()
    try:
        got = db.execute(text("""SELECT data_type, numeric_precision, numeric_scale FROM information_schema.columns
                                  WHERE table_name = 'final_recon_deals' AND column_name = :c"""), {"c": col}).first()
    finally:
        db.close()
    assert tuple(got) == ("numeric", 14, 2), col
