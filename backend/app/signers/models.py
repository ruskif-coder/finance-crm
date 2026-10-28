# -*- coding: utf-8 -*-
"""Подписанты. Таблицы — миграция `2026-10-28_signers.sql`; модели зарегистрированы в `model_registry`."""
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class CounterpartySigner(Base):
    """Подписант юрлица: ФИО, должность, основание полномочий, срок доверенности. Один у юрлица — по умолчанию."""
    __tablename__ = "counterparty_signers"
    id = Column(Integer, primary_key=True)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id", ondelete="CASCADE"), nullable=False)
    director_name = Column(Text)
    signer_position = Column(Text)
    signer_basis = Column(Text)
    valid_until = Column(Date)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    is_archived = Column(Boolean, nullable=False, default=False, server_default="false")
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))


class ContractSigner(Base):
    """Кто подписывает договор со стороны заказчика / исполнителя. Нет строки — подписант юрлица по умолчанию."""
    __tablename__ = "contract_signers"
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True)
    side = Column(String(12), primary_key=True)
    signer_id = Column(Integer, ForeignKey("counterparty_signers.id"), nullable=False)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))
