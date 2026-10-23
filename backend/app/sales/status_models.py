# -*- coding: utf-8 -*-
"""Модели «Статусов продаж» (миграция backend/migrations/2026-10-22_sales_status.sql, состав согласован с владельцем 22.10.2026)."""
from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY

from app.database import Base

MEETINGS = ("предложена", "подтверждена")
FIELDS = ("meet_brand", "meet_agency", "comment_sales", "comment_head")


class SalesStatusNote(Base):
    """Строка «Статусов продаж» на бренд: встречи и комментарии, которых нет в сделке. Одна текущая запись на пару
    «рекламодатель + бренд» (бренд пуст — строка рекламодателя) или на клиента из Excel вне справочника (`client_name`)."""
    __tablename__ = "sales_status_notes"
    # Те же ограничения, что в миграции: если таблицу создаст create_all раньше неё, они не потеряются (ревью 22.10.2026)
    __table_args__ = (
        CheckConstraint("(advertiser_id IS NOT NULL) <> (client_name IS NOT NULL)", name="ck_sales_status_note_owner"),
        CheckConstraint("meet_brand IN ('предложена', 'подтверждена')", name="ck_sales_status_note_meet_brand"),
        CheckConstraint("meet_agency IN ('предложена', 'подтверждена')", name="ck_sales_status_note_meet_agency"),
    )
    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id", ondelete="CASCADE"))
    brand_id = Column(Integer, ForeignKey("sales_brands.id", ondelete="CASCADE"))
    client_name = Column(String(300))
    meet_brand = Column(String(12))
    meet_agency = Column(String(12))
    comment_sales = Column(Text)
    comment_head = Column(Text)
    from_excel = Column(ARRAY(Text), nullable=False, server_default="{}")
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class SalesStatusReminder(Base):
    """Будильник на строку «Статусов продаж» (миграция 2026-10-23_sales_status_reminders.sql, владелец 23.10.2026): человек
    ставит себе дату — в 09:00 МСК этого дня напоминание уходит в Telegram и на почту. Один на строку у каждого."""
    __tablename__ = "sales_status_reminders"
    __table_args__ = (
        CheckConstraint("(advertiser_id IS NOT NULL) <> (client_name IS NOT NULL)", name="ck_ssr_owner"),
        CheckConstraint("brand_id IS NULL OR advertiser_id IS NOT NULL", name="ck_ssr_brand"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id", ondelete="CASCADE"))
    brand_id = Column(Integer, ForeignKey("sales_brands.id", ondelete="CASCADE"))
    client_name = Column(String(300))
    remind_on = Column(Date, nullable=False)
    note = Column(Text)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
