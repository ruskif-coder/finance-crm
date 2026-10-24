# -*- coding: utf-8 -*-
"""Модели «Плана продаж» (миграция backend/migrations/2026-10-24_sales_plan.sql, схема согласована с владельцем 24.10.2026)."""
from sqlalchemy import (CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text,
                        UniqueConstraint, func)

from app.database import Base

SCOPES = ("общий", "услуга", "продажник")


class SalesTarget(Base):
    """Цель продаж: месяц × разрез, руб. без НДС. Разрезы независимые; год и кварталы — суммы месяцев."""
    __tablename__ = "sales_targets"
    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_sales_target_month"),
        CheckConstraint("scope IN ('общий', 'услуга', 'продажник')", name="ck_sales_target_scope"),
        CheckConstraint("amount >= 0", name="ck_sales_target_amount"),
        UniqueConstraint("year", "month", "scope", "service_id", "sales_rep_id", name="uq_sales_target",
                         postgresql_nulls_not_distinct=True),
    )
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    month = Column(SmallInteger, nullable=False)
    scope = Column(Text, nullable=False)
    service_id = Column(Integer, ForeignKey("sales_services.id"))
    sales_rep_id = Column(Integer, ForeignKey("sales_reps.id"))
    amount = Column(Numeric(14, 2), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SalesPlanSnapshot(Base):
    """Ночной снимок выполнения и прогноза ячейки — для «▲▼ за 7 дней». key_id 0 — общий и строки «без …»."""
    __tablename__ = "sales_plan_snapshots"
    day = Column(Date, primary_key=True)
    year = Column(Integer, primary_key=True)
    month = Column(SmallInteger, primary_key=True)
    scope = Column(Text, primary_key=True)
    key_id = Column(Integer, primary_key=True, default=0)
    done = Column(Numeric(14, 2), nullable=False)
    forecast = Column(Numeric(14, 2), nullable=False)
