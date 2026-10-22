# -*- coding: utf-8 -*-
"""Данные закрытия сделки. Таблица создаётся миграцией `2026-10-14_sk_mode.sql`; модель зарегистрирована в `model_registry`."""
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base

SK_MODES = ("постоплата", "скидка в счёт")


class FinalReconDeal(Base):
    """СК сделки на закрытии: подставляется от плательщика, правится аккаунтом; дальше не зависит от настроек юрлица."""
    __tablename__ = "final_recon_deals"
    deal_id = Column(Integer, ForeignKey("sales_deals.id"), primary_key=True)
    sk_mode = Column(String(16))
    sk_percent = Column(Float)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    # Итоговая сверка (миграция 2026-10-15_closing_contour.sql): пин суммы ДС и цифры, замороженные на «Отправить в ДО».
    ds_mode = Column(String(8))            # fact / plan / manual; пусто — по умолчанию
    ds_manual_net = Column(Float)          # ручная сумма базовой услуги без НДС (мастер/админ)
    ds_manual_volume = Column(BigInteger)  # ручное количество единиц — связано с суммой через цену за единицу МП
    plan_shows = Column(BigInteger)
    fact_shows = Column(BigInteger)
    bonus_shows = Column(BigInteger)
    base_net = Column(Float)
    sent_at = Column(DateTime)
    sent_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)        # «Подтвердить сверку»; снимается сменой режима, скидки, ручной суммы
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    cost_net = Column(Numeric(14, 2))      # себестоимость без НДС — вносит аккаунт на закрытии (19.10.2026)
    # «Закрыть без документов» — бонусное размещение (миграция 2026-10-19_closing_no_docs.sql)
    closed_no_docs_at = Column(DateTime)
    closed_no_docs_by = Column(Integer, ForeignKey("users.id"))


class FinalReconFactEntry(Base):
    """Факт, введённый аккаунтом по строке МП, — для услуг без РК (миграция `2026-10-19_final_recon_fact_entries.sql`)."""
    __tablename__ = "final_recon_fact_entries"
    __table_args__ = (UniqueConstraint("deal_id", "mp_row_id", name="uq_fact_entry_row"),)
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"), nullable=False)
    mp_row_id = Column(Integer, nullable=False)
    fact_volume = Column(Numeric(16, 2), nullable=False)
    source_note = Column(String(300))
    # Схема приёмки по модели строки (миграция 2026-10-19_final_recon_fact_metrics.sql)
    fact_clicks = Column(BigInteger)
    fact_views_completed = Column(BigInteger)     # досмотры 100 % (видео); VTR не хранится
    fact_reference_shows = Column(BigInteger)     # показы справочно у фикса — на деньги не влияют
    entered_by = Column(Integer, ForeignKey("users.id"))
    entered_at = Column(DateTime, nullable=False, server_default=func.now())
