"""
SQLAlchemy-модели дашборда продаж.

Соответствуют scripts/sales_dashboard_schema.sql один в один. Схема применяется
вручную через psql (Alembic в проекте не используется); create_all при старте
только досоздаёт отсутствующее и никогда не изменяет существующие таблицы.

Деньги — Float (double precision), однородно с Operation.income/expense.
Точная арифметика разнесения и округления ведётся в Decimal на стороне Python
(см. app/sales/periods.py, app/sales/allocation.py): плавающие копейки рождаются
в вычислениях, а не в хранении.
"""
from sqlalchemy import (Column, Integer, String, Float, Date, DateTime, Boolean,
                        Text, ForeignKey, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ============================ СПРАВОЧНИКИ ============================

class SalesServiceGroup(Base):
    __tablename__ = "sales_service_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)


class SalesService(Base):
    __tablename__ = "sales_services"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    group = Column("group", String)  # денормализовано строкой, как Article.group
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text)


class SalesAdvertiser(Base):
    __tablename__ = "sales_advertisers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    # NULL намеренно: рекламодатель и плательщик — разные сущности.
    # Пусто = платит агентство, нормальное состояние, а не пропуск данных.
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    inn = Column(String)
    # перенос листа MP Advertisers — исключение «МП» из выручки
    exclude_from_revenue = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text)
    brands = relationship("SalesBrand", back_populates="advertiser")


class SalesBrand(Base):
    __tablename__ = "sales_brands"
    __table_args__ = (UniqueConstraint("advertiser_id", "name"),)
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    advertiser = relationship("SalesAdvertiser", back_populates="brands")


class SalesPriceListItem(Base):
    __tablename__ = "sales_price_list"
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("sales_services.id"), nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="RUB")
    valid_from = Column(Date)
    valid_to = Column(Date)
    unit = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text)


class SalesRep(Base):
    __tablename__ = "sales_reps"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    bitrix_user_id = Column(String, unique=True)
    # NULL: менеджер в Битриксе не обязан быть пользователем финмодуля
    user_id = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, nullable=False, default=True)


class SalesPipeline(Base):
    __tablename__ = "sales_pipelines"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


# ===================== АЛЬТЕРНАТИВНЫЕ ГРУППИРОВКИ =====================

class SalesGroupingScheme(Base):
    """Способ нарезки справочника. Схем на один справочник может быть несколько:
    услуги по типу инвентаря И те же услуги по маржинальности."""
    __tablename__ = "sales_grouping_schemes"
    __table_args__ = (UniqueConstraint("entity", "name"),)
    id = Column(Integer, primary_key=True)
    entity = Column(String, nullable=False)  # service | advertiser | brand
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    buckets = relationship("SalesGroupingBucket", back_populates="scheme",
                           cascade="all, delete-orphan")


class SalesGroupingBucket(Base):
    __tablename__ = "sales_grouping_buckets"
    __table_args__ = (UniqueConstraint("scheme_id", "name"),)
    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey("sales_grouping_schemes.id", ondelete="CASCADE"),
                       nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    scheme = relationship("SalesGroupingScheme", back_populates="buckets")
    members = relationship("SalesGroupingMember", back_populates="bucket",
                           cascade="all, delete-orphan")


class SalesGroupingMember(Base):
    __tablename__ = "sales_grouping_members"
    __table_args__ = (UniqueConstraint("bucket_id", "entity_id"),)
    id = Column(Integer, primary_key=True)
    bucket_id = Column(Integer, ForeignKey("sales_grouping_buckets.id", ondelete="CASCADE"),
                       nullable=False)
    # Без FK: таблица-цель зависит от scheme.entity, целостность проверяется в приложении.
    entity_id = Column(Integer, nullable=False)
    bucket = relationship("SalesGroupingBucket", back_populates="members")


# ======================= СТАДИИ И ПОЛНОТА ДАННЫХ =======================

class SalesBitrixStageMap(Base):
    """Раскладка (воронка, стадия) → слой денег. Хранится данными, а не в коде:
    названия стадий содержат имена сотрудников и меняются без нашего участия."""
    __tablename__ = "sales_bitrix_stage_map"
    __table_args__ = (UniqueConstraint("pipeline", "bitrix_stage"),)
    id = Column(Integer, primary_key=True)
    pipeline = Column(String, nullable=False)
    bitrix_stage = Column(String, nullable=False)
    stage_key = Column(String, nullable=False)
    money_layer = Column(String, nullable=False)  # планируемые | реализуемые | фактические
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class SalesStageRequirement(Base):
    """Контроль полноты: по мере продвижения сделки набор обязательных полей растёт."""
    __tablename__ = "sales_stage_requirements"
    __table_args__ = (UniqueConstraint("pipeline", "stage_key", "required_field"),)
    id = Column(Integer, primary_key=True)
    pipeline = Column(String, nullable=False)
    stage_key = Column(String, nullable=False)
    required_field = Column(String, nullable=False)
    is_blocking = Column(Boolean, nullable=False, default=False)


# ========================= СДЕЛКИ И ПРИЛОЖЕНИЯ =========================

class SalesAnnex(Base):
    """Приложение к договору — рождается при переходе сделки в стадию «Запуск».
    Наше юрлицо не дублируется: выводится из contracts.own_company_id."""
    __tablename__ = "sales_annexes"
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    number = Column(String)
    date = Column(Date)
    total_amount = Column(Float)
    currency = Column(String, nullable=False, default="RUB")
    status = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    items = relationship("SalesAnnexItem", back_populates="annex",
                         cascade="all, delete-orphan")


class SalesDeal(Base):
    """Read-model медиаплана из Битрикс24.

    Слой денег НЕ хранится колонкой: выводится джойном на sales_bitrix_stage_map,
    иначе правка маппинга не влияла бы на уже загруженные сделки."""
    __tablename__ = "sales_deals"
    id = Column(Integer, primary_key=True)
    bitrix_id = Column(String, nullable=False, unique=True)
    title = Column(String)
    pipeline = Column(String)
    bitrix_stage = Column(String)
    amount = Column(Float)
    currency = Column(String, nullable=False, default="RUB")
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"))
    # Одиночная ссылка: один медиаплан — один бренд. Несколько брендов дают
    # несколько медиапланов, сливающихся в одно приложение на «Сборе запуска».
    brand_id = Column(Integer, ForeignKey("sales_brands.id"))
    # Две разные роли, обе из справочника sales_reps и в данных не пересекаются:
    # продавец закреплён за клиентом (колонка CJ), аккаунт-менеджер ведёт сделку
    # со «Сбора запуска» и далее (колонка BI «Ответственный КС»).
    sales_rep_id = Column(Integer, ForeignKey("sales_reps.id"))
    account_manager_id = Column(Integer, ForeignKey("sales_reps.id"))
    annex_id = Column(Integer, ForeignKey("sales_annexes.id"))
    date_create = Column(DateTime)
    date_modify = Column(DateTime)
    # Период размещения — «Старт РК» / «Конец РК». Основная ось витрины:
    # дата создания сделки для отчётности бесполезна, деньги относятся
    # к периоду размещения. period_to = NULL — календарный месяц period_from.
    period_from = Column(Date)
    period_to = Column(Date)
    synced_at = Column(DateTime, server_default=func.now())


class SalesAnnexItem(Base):
    """Состав микса: бренд × услуга × сумма × период размещения.
    period_to = NULL означает календарный месяц period_from."""
    __tablename__ = "sales_annex_items"
    id = Column(Integer, primary_key=True)
    annex_id = Column(Integer, ForeignKey("sales_annexes.id", ondelete="CASCADE"), nullable=False)
    service_id = Column(Integer, ForeignKey("sales_services.id"), nullable=False)
    brand_id = Column(Integer, ForeignKey("sales_brands.id"))
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="RUB")
    period_from = Column(Date)
    period_to = Column(Date)
    annex = relationship("SalesAnnex", back_populates="items")


class SalesDealAnnexAllocation(Base):
    """Разнесение суммы приложения по исходным медиапланам.

    Многие-к-одному С СУММАМИ: без них невозможно вернуть выручку исходным
    авторам, а значит невозможно посчитать бонусы разных менеджеров
    по общему приложению."""
    __tablename__ = "sales_deal_annex_allocation"
    __table_args__ = (UniqueConstraint("deal_id", "annex_id"),)
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"), nullable=False)
    annex_id = Column(Integer, ForeignKey("sales_annexes.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)


# ============================== СЛУЖЕБНЫЕ ==============================

class SalesBitrixRaw(Base):
    """APPEND-ONLY. Новая версия пишется только при смене payload_hash.

    Суммы в сделке правятся на фактические при закрытии; без истории версий
    план-факт с прогнозом невозможен — сравнивать не с чем."""
    __tablename__ = "sales_bitrix_raw"
    id = Column(Integer, primary_key=True)
    entity = Column(String, nullable=False)
    bitrix_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    payload_hash = Column(String, nullable=False)
    fetched_at = Column(DateTime, server_default=func.now())


class SalesBitrixSyncLog(Base):
    __tablename__ = "sales_bitrix_sync_log"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    status = Column(String, nullable=False)  # running | success | error
    entity = Column(String)
    fetched = Column(Integer, nullable=False, default=0)
    created = Column(Integer, nullable=False, default=0)
    updated = Column(Integer, nullable=False, default=0)
    rejected = Column(Integer, nullable=False, default=0)
    error_text = Column(Text)
    triggered_by = Column(Integer, ForeignKey("users.id"))


class SalesMatchQueue(Base):
    """Очередь ручного сопоставления. Никакого нечёткого матчинга:
    0 или >1 кандидатов — строка сюда, а не догадка."""
    __tablename__ = "sales_match_queue"
    id = Column(Integer, primary_key=True)
    entity = Column(String, nullable=False)  # counterparty | service | brand | advertiser | stage
    raw_value = Column(String, nullable=False)
    candidates = Column(JSONB)
    reason = Column(String)  # no_inn | not_found | ambiguous
    resolved_id = Column(Integer)
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
