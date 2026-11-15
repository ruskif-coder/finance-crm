# -*- coding: utf-8 -*-
"""ORM проверки баннера после заливки в DSP (владелец 15.11.2026).

Таблицу создаёт миграция `migrations/2026-11-15_dsp_banner_check.sql`; здесь только маппинг. Строка на креатив РК —
последнее состояние: `checked_at` пусто = в очереди, `ok`/`problems` — итог по разметке с отпечатком `html_hash`.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

import app.ad.models  # noqa: F401 — таблица креатива РК для внешнего ключа
from app.database import Base


class DspBannerCheck(Base):
    __tablename__ = "dsp_banner_check"

    id = Column(Integer, primary_key=True)
    creative_id = Column(Integer, ForeignKey("ad_campaign_creative.id", ondelete="CASCADE"), nullable=False, unique=True)
    html_hash = Column(String(64))
    checked_at = Column(DateTime)
    ok = Column(Boolean)
    problems = Column(JSONB)
