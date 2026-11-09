# -*- coding: utf-8 -*-
"""Премодерация SSP: пакет (креатив), заявка SSP, наше решение, заказчик премодерации.

Создаются миграцией 2026-11-07_premoderation.sql. Модели зарегистрированы в `model_registry`.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func

from app.database import Base

APPROVED = "одобрено"
DECLINED = "отклонено"
VERDICTS = (APPROVED, DECLINED)


class PremodPackage(Base):
    __tablename__ = "premod_package"

    id = Column(Integer, primary_key=True)
    image_hash = Column(String(64), nullable=False, unique=True)
    size = Column(String(16))
    kind = Column(String(16))
    advertiser_name = Column(Text)
    advertiser_inn = Column(String(12))
    snapshot_token = Column(String(64))
    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    text = Column(Text)
    checks = Column(JSONB, nullable=False, default=list)
    prev_package_id = Column(Integer, ForeignKey("premod_package.id"))
    changes = Column(JSONB)


class PremodRequest(Base):
    __tablename__ = "premod_request"

    id = Column(Integer, primary_key=True)
    ssp_uuid = Column(String(64), nullable=False, unique=True)
    package_id = Column(Integer, ForeignKey("premod_package.id"))
    erid = Column(String(64))
    crid = Column(String(128))
    ssp_publishers = Column(ARRAY(Integer), nullable=False, default=list)
    ssp_status = Column(SmallInteger)
    ssp_updated_at = Column(DateTime)
    ssp_moderated_by = Column(Text)
    preview_url = Column(Text)
    click_url = Column(Text)
    landing = Column(Text)
    checks = Column(JSONB, nullable=False, default=list)
    fetched_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now())


class PremodDecision(Base):
    __tablename__ = "premod_decision"

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("premod_request.id"), nullable=False)
    image_hash = Column(String(64), nullable=False)
    verdict = Column(String(16), nullable=False)
    reason_code = Column(Integer)
    reason_label = Column(Text)
    comment = Column(Text)
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    decided_at = Column(DateTime, nullable=False, server_default=func.now())
    followed_package = Column(Boolean)
    sent_at = Column(DateTime)
    bulk = Column(Boolean, nullable=False, default=False)


class PremodAdvertiser(Base):
    """Заказчик премодерации — не наш рекламодатель, свой справочник: короткое имя и категория."""
    __tablename__ = "premod_advertiser"

    inn = Column(String(12), primary_key=True)
    short_name = Column(Text)
    category = Column(Text)
