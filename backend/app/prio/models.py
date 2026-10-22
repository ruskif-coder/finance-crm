# -*- coding: utf-8 -*-
"""Приоритезация (владелец 19.10.2026). Таблицы — миграция `2026-10-19_prioritization.sql`; регистрация — `model_registry`.

Запрос по сделке — общая часть для всех площадок (собирает аккаунт); площадка запроса — пара «сделка × площадка» = одна РК
в системе приоритезации; снимки суточной статистики — с дельтой к предыдущему снимку того же дня."""
from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base

# Статусы площадки запроса. «идёт» ⇄ «остановлено» — кнопками Стоп / Старт; «отказ» — конечный (площадка отказала).
DRAFT, AT_SITE, REWORK, APPROVED, LIVE, STOPPED, REJECTED = (
    "черновик", "у площадки", "правки", "согласовано", "идёт", "остановлено", "отказ")
STATUSES = (DRAFT, AT_SITE, REWORK, APPROVED, LIVE, STOPPED, REJECTED)


class PrioRequest(Base):
    __tablename__ = "prio_requests"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"), nullable=False, unique=True)
    product_name = Column(String(300))
    target_competitors = Column(Text)
    target_mnn = Column(Text)
    target_meta = Column(Text)
    date_start = Column(Date)
    date_end = Column(Date)
    erid_meta = Column(String(300))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))


class PrioPlacement(Base):
    __tablename__ = "prio_placements"
    __table_args__ = (UniqueConstraint("request_id", "publisher_id", name="uq_prio_placement"),)
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("prio_requests.id", ondelete="CASCADE"), nullable=False)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id"), nullable=False)
    product_id = Column(String(64))          # SKU — вписывает площадка
    product_url = Column(String(1000))       # посадочная — вписывает аккаунт
    goal_imp = Column(BigInteger)
    erid = Column(String(64))
    status = Column(String(20), nullable=False, server_default=DRAFT)
    camp_id = Column(Integer)
    tracker = Column(JSONB)
    toggle_on = Column(Boolean)
    comment = Column(Text)
    comment_by = Column(Integer, ForeignKey("users.id"))
    comment_at = Column(DateTime)
    sent_at = Column(DateTime)
    approved_at = Column(DateTime)
    launched_at = Column(DateTime)
    reminded_at = Column(DateTime)
    rejected_at = Column(DateTime)
    goal_reached_at = Column(DateTime)      # автостоп по плану — app/prio/autostop.py
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class PrioStatRaw(Base):
    __tablename__ = "prio_stat_raw"
    id = Column(Integer, primary_key=True)
    camp_id = Column(Integer, nullable=False)
    day = Column(Date, nullable=False)
    shows = Column(BigInteger, nullable=False, server_default="0")
    clicks = Column(BigInteger, nullable=False, server_default="0")
    by_type = Column(JSONB)
    delta_shows = Column(BigInteger)
    delta_clicks = Column(BigInteger)
    pulled_at = Column(DateTime, nullable=False, server_default=func.now())
