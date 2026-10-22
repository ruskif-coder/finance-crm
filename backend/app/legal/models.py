# -*- coding: utf-8 -*-
"""Заявки юристу. Таблица создаётся миграцией `2026-10-14_legal_requests.sql`; модель зарегистрирована в `model_registry`."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base

OPEN = ("открыта", "в работе")       # такие заявки блокируют выпуск своего ДС


class LegalRequest(Base):
    """Заявка аккаунта юристу по пункту ДС после таблицы МП; правка ложится в кастомный шаблон ДС договора."""
    __tablename__ = "legal_requests"
    id = Column(Integer, primary_key=True)
    annex_id = Column(Integer, ForeignKey("sales_annexes.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    block_id = Column(Text)                              # пусто — добавить новый пункт
    text = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="открыта")
    answer = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    taken_by = Column(Integer, ForeignKey("users.id"))
    taken_at = Column(DateTime)
    closed_by = Column(Integer, ForeignKey("users.id"))
    closed_at = Column(DateTime)
    result_version_id = Column(Integer)                 # FK на версию шаблона ДС держит база (миграция): таблицы шаблонов — только пакет annex_tpl
