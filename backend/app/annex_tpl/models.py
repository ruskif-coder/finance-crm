# -*- coding: utf-8 -*-
"""Таблицы шаблонов ДС. Создаются миграцией `2026-10-13_annex_templates.sql`; модели зарегистрированы в `model_registry`."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class AnnexTplTemplate(Base):
    """«Ячейка» шаблона: базовый (именованный) или кастомный под договор. Текущая версия не хранится."""
    __tablename__ = "annex_tpl_templates"
    id = Column(Integer, primary_key=True)
    scope = Column(String(8), nullable=False)            # base | custom
    title = Column(Text)                                 # только у базового
    contract_id = Column(Integer, ForeignKey("contracts.id"))                  # только у кастомного
    base_template_id = Column(Integer, ForeignKey("annex_tpl_templates.id"))   # только у кастомного
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))


class AnnexTplFormat(Base):
    """Формат сотрудничества договора → базовый шаблон, который его обслуживает (один формат — один шаблон)."""
    __tablename__ = "annex_tpl_formats"
    format = Column(Text, primary_key=True)
    template_id = Column(Integer, ForeignKey("annex_tpl_templates.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AnnexTplVersion(Base):
    """Версия шаблона. Только добавление: правку запрещает триггер в базе и тест."""
    __tablename__ = "annex_tpl_versions"
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("annex_tpl_templates.id"), nullable=False)
    version = Column(Integer, nullable=False)
    blocks = Column(JSONB, nullable=False)
    changes = Column(JSONB, nullable=False, default=list)
    base_version = Column(Integer)                       # только у кастомного
    restored_from = Column(Integer)
    author_id = Column(Integer, ForeignKey("users.id"))
    author_name = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
