# -*- coding: utf-8 -*-
"""Мастер-сделка — юридическая обёртка под ДС (владелец 15.10.2026). Таблицы создаёт миграция `2026-10-15_closing_contour.sql`;
модели зарегистрированы в `model_registry`. Заводится всегда, даже на одну сделку; ключ — доходный договор и финансовый месяц."""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base

from app.master_deal.status import STATUSES  # noqa: E402,F401 — порядок и смысл статусов живут там
BONUS_ADDONS = ("zero", "hide")


class MasterDeal(Base):
    __tablename__ = "master_deals"
    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)        # сквозной M-0001
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    period = Column(String(7), nullable=False)                     # YYYY-MM
    payer_counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    status = Column(String(20), nullable=False, default="черновик", server_default="черновик")
    addons_separate = Column(Boolean, nullable=False, default=True, server_default="true")
    bonus_addons = Column(String(8), nullable=False, default="zero", server_default="zero")
    ds_by_brand = Column(Boolean, nullable=False, default=True, server_default="true")
    ds_by_service = Column(Boolean, nullable=False, default=True, server_default="true")
    upd_by_brand = Column(Boolean, nullable=False, default=True, server_default="true")
    upd_by_service = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime)
    # Раскладка (миграция 2026-10-15_closing_contour.sql, п. 9): к ней возвращаются и правят, пока ДС пакета не выпущен.
    start_no = Column(Integer)                     # последний актуальный № ДС по договору; ДС пакета — от следующего
    moved = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))   # id строк-допов, перенесённых в основной ДС
    saved_by = Column(Integer, ForeignKey("users.id"))
    # Выставление (2026-10-19_master_deal_issue.sql): ЭДО — отправкой закрыты документы; бумага — подпись у нас, отправка, сканы.
    signed_by_us_at = Column(DateTime)
    signed_by_us_by = Column(Integer, ForeignKey("users.id"))
    sent_at = Column(DateTime)
    sent_by = Column(Integer, ForeignKey("users.id"))
    track_no = Column(String(64))
    docs_closed_at = Column(DateTime)
    docs_closed_by = Column(Integer, ForeignKey("users.id"))


class MasterDealItem(Base):
    __tablename__ = "master_deal_items"
    id = Column(Integer, primary_key=True)
    master_deal_id = Column(Integer, ForeignKey("master_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id"), nullable=False, unique=True)   # максимум в одном пакете
    added_by = Column(Integer, ForeignKey("users.id"))
    added_at = Column(DateTime, nullable=False, server_default=func.now())


class MasterDealUpd(Base):
    """Комплект закрывающих: одна УПД = одно основание; № сквозной в рамках мастер-сделки."""
    __tablename__ = "master_deal_upds"
    __table_args__ = (UniqueConstraint("master_deal_id", "upd_no"),)
    id = Column(Integer, primary_key=True)
    master_deal_id = Column(Integer, ForeignKey("master_deals.id", ondelete="CASCADE"), nullable=False)
    upd_no = Column(Integer, nullable=False)
    annex_id = Column(Integer, ForeignKey("sales_annexes.id"))
    brand = Column(String(200))
    service = Column(String(200))
    net = Column(Float, nullable=False, default=0)
    vat = Column(Float, nullable=False, default=0)
    gross = Column(Float, nullable=False, default=0)
    basis_text = Column(Text)
    onec_net = Column(Float)
    onec_at = Column(DateTime)
    onec_invoice_no = Column(String(40))     # № счёта, выпущенного 1С (2026-10-19_master_deal_upd_onec_numbers.sql)
    onec_upd_no = Column(String(40))         # № УПД, выпущенного 1С
    onec_invoice_date = Column(Date)         # дата счёта в 1С (2026-10-20_master_deal_operation_bridge.sql)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class MasterDealFile(Base):
    """Скан подписанного бумажного документа пакета — один файл к одному ДС или одному УПД (2026-10-19_master_deal_issue.sql,
    привязка — 2026-10-19_master_deal_scans_per_doc.sql)."""
    __tablename__ = "master_deal_files"
    id = Column(Integer, primary_key=True)
    master_deal_id = Column(Integer, ForeignKey("master_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="скан ДС", server_default="скан ДС")   # скан ДС | скан УПД
    annex_id = Column(Integer, ForeignKey("sales_annexes.id", ondelete="CASCADE"))      # скан ДС (2026-10-19_master_deal_scans_per_doc.sql)
    upd_no = Column(Integer)                                                           # скан УПД № в пакете
    filename = Column(String(300), nullable=False)
    path = Column(String(500), nullable=False)
    size = Column(Integer)
    content_type = Column(String(120))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now())
