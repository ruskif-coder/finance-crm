# -*- coding: utf-8 -*-
"""Таблицы «Агентских условий» — миграция `2026-10-27_agency_terms.sql`."""
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text

from app.database import Base


class SkRule(Base):
    """Правило СК: основная или партнёрская, набор необязательных признаков (`agency_terms.rules`)."""
    __tablename__ = "sk_rules"
    id = Column(Integer, primary_key=True)
    kind = Column(String(12), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    agency_id = Column(Integer, ForeignKey("sales_agencies.id"))
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"))
    brand_id = Column(Integer, ForeignKey("sales_brands.id"))
    service_id = Column(Integer, ForeignKey("sales_services.id"))
    recipient_id = Column(Integer, ForeignKey("counterparties.id"))
    mode = Column(String(16), nullable=False)
    percent = Column(Numeric(5, 2), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime)
    updated_by = Column(Integer, ForeignKey("users.id"))


class SkSpecialTerm(Base):
    """Спец. условие — скрытая вкладка (право `sk_special`), в общий расчёт не входит."""
    __tablename__ = "sk_special_terms"
    id = Column(Integer, primary_key=True)
    scope_kind = Column(String(16), nullable=False)
    scope_id = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    percent = Column(Numeric(5, 2))
    amount = Column(Numeric(14, 2))
    threshold = Column(Numeric(14, 2))     # порог оборота за год (только у %): до него «копится», после — % со всего года
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime)
    updated_by = Column(Integer, ForeignKey("users.id"))


class SkMonth(Base):
    """Закрытый месяц: дальше читается из снимка `sk_accruals`."""
    __tablename__ = "sk_months"
    period = Column(String(7), primary_key=True)
    closed_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_by = Column(Integer, ForeignKey("users.id"))
    note = Column(Text)


class SkAccrual(Base):
    """Снимок СК закрытого месяца: сделка × вид (× получатель у партнёрской)."""
    __tablename__ = "sk_accruals"
    id = Column(Integer, primary_key=True)
    period = Column(String(7), ForeignKey("sk_months.period", ondelete="CASCADE"), nullable=False)
    deal_id = Column(Integer, ForeignKey("sales_deals.id"), nullable=False)
    master_deal_id = Column(Integer, ForeignKey("master_deals.id"))
    kind = Column(String(12), nullable=False)
    rule_id = Column(Integer, ForeignKey("sk_rules.id"))
    recipient_id = Column(Integer, ForeignKey("counterparties.id"))
    mode = Column(String(16))
    percent = Column(Numeric(5, 2))
    base_net = Column(Numeric(14, 2), nullable=False)
    amount_net = Column(Numeric(14, 2))


class SkWorkTerm(Base):
    """«Условия работы» — договорённости для аккаунта при сборке медиаплана (показ — плашкой под брифом)."""
    __tablename__ = "sk_work_terms"
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    agency_id = Column(Integer, ForeignKey("sales_agencies.id"))
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"))
    brand_id = Column(Integer, ForeignKey("sales_brands.id"))
    service_id = Column(Integer, ForeignKey("sales_services.id"))
    body = Column(Text, nullable=False)
    mail_subject = Column(Text)
    commit_net = Column(Numeric(14, 2))
    comment = Column(Text)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    # бонусы для аккаунта (миграция 2026-10-27_work_terms_bonus.sql): флажок + при каком условии
    creatives_bonus = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    creatives_bonus_note = Column(Text)
    reports_bonus = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    reports_bonus_note = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime)
    updated_by = Column(Integer, ForeignKey("users.id"))
