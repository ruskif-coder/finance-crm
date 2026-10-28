# -*- coding: utf-8 -*-
"""Таблицы шаблонов ДС. Создаются миграциями `2026-10-13_annex_templates.sql` и `2026-10-27_annex_tpl_named.sql` (несколько именованных
шаблонов на договор, основной, память «бренд → шаблон»); модели зарегистрированы в `model_registry`."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class AnnexTplTemplate(Base):
    """«Ячейка» шаблона: базовый (именованный) или шаблон договора (именованный, их у договора может быть несколько). Текущая версия не хранится."""
    __tablename__ = "annex_tpl_templates"
    id = Column(Integer, primary_key=True)
    scope = Column(String(8), nullable=False)            # base | custom
    title = Column(Text, nullable=False)                 # вариант договора у базового, имя у шаблона договора
    contract_id = Column(Integer, ForeignKey("contracts.id"))                  # только у кастомного
    base_template_id = Column(Integer, ForeignKey("annex_tpl_templates.id"))   # только у кастомного
    is_main = Column(Boolean, nullable=False, default=False, server_default="false")   # основной шаблон договора
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


class AnnexTplBrandMemory(Base):
    """Договор + бренд → шаблон, по которому последним подтверждён ДС с этим брендом: подставляется в следующий ДС бренда."""
    __tablename__ = "annex_tpl_brand_memory"
    contract_id = Column(Integer, ForeignKey("contracts.id"), primary_key=True)
    brand_id = Column(Integer, ForeignKey("sales_brands.id"), primary_key=True)
    template_id = Column(Integer, ForeignKey("annex_tpl_templates.id"), nullable=False)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))
