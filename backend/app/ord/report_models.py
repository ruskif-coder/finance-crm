# -*- coding: utf-8 -*-
"""Отчёт ОРД за месяц: снимок разреза DSP по креативу и правки из Excel. Таблицы — миграция
`backend/migrations/2026-11-11_ord_month_report.sql` (состав согласован владельцем 11.11.2026)."""
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class OrdEridMonthStat(Base):
    __tablename__ = "ord_erid_month_stat"
    __table_args__ = (UniqueConstraint("month", "placement_id", "creative_id", name="uq_ord_erid_month_stat"),)
    id = Column(Integer, primary_key=True)
    month = Column(Date, nullable=False)
    placement_id = Column(Integer, ForeignKey("ad_campaign_placement.id", ondelete="CASCADE"), nullable=False)
    creative_id = Column(Integer, ForeignKey("ad_campaign_creative.id", ondelete="CASCADE"))
    erid = Column(String(64))
    shows = Column(BigInteger, nullable=False, default=0)
    clicks = Column(BigInteger, nullable=False, default=0)
    captured_at = Column(DateTime, nullable=False, server_default=func.now())


class OrdReportOverride(Base):
    __tablename__ = "ord_report_overrides"
    id = Column(Integer, primary_key=True)
    month = Column(Date, nullable=False)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"))
    deal_code = Column(String(16), nullable=False)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="SET NULL"))
    domain = Column(String(255), nullable=False, default="")
    erid = Column(String(255), nullable=False, default="")
    kind = Column(String(16), nullable=False)
    shows = Column(BigInteger)
    clicks = Column(BigInteger)
    amount = Column(Numeric(14, 2))
    upd_no = Column(String(40))
    upd_date = Column(Date)
    upd_gross = Column(Numeric(14, 2))
    imported_at = Column(DateTime, nullable=False, server_default=func.now())
    imported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    filename = Column(String(255))
