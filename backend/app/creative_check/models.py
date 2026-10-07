# -*- coding: utf-8 -*-
"""Проверка креатива (аккаунты): одна таблица, история не хранится — проверка живёт 48 часов.

Создаётся миграцией 2026-10-07_creative_check.sql. Модель зарегистрирована в `model_registry`.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func

from app.database import Base

LIFETIME_HOURS = 48


class CreativeCheck(Base):
    __tablename__ = "creative_check"

    id = Column(Integer, primary_key=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(Text, nullable=False)
    advertiser_url = Column(Text, nullable=False)
    kind = Column(String(8), nullable=False)               # image | html5
    original_name = Column(Text)
    file_path = Column(Text, nullable=False)                # подготовленный архив
    verdict = Column(JSONB, nullable=False, default=dict)
    publisher_ids = Column(ARRAY(Integer), nullable=False, default=list)
    sandbox_token = Column(String(64))
    entry_path = Column(Text)
    dsp_xxhash = Column(String(64))
    dsp_state = Column(String(16))                          # NULL | live | stopped
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
