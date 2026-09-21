"""
SQLAlchemy-модели дашборда продаж.

Соответствуют scripts/2026-07-23_sales_dashboard_schema.sql один в один. Схема применяется
вручную через psql (Alembic в проекте не используется); create_all при старте
только досоздаёт отсутствующее и никогда не изменяет существующие таблицы.

Деньги — Float (double precision), однородно с Operation.income/expense.
Точная арифметика разнесения и округления ведётся в Decimal на стороне Python
(см. app/sales/periods.py, app/sales/periods.py): плавающие копейки рождаются
в вычислениях, а не в хранении.
"""
from sqlalchemy import (Column, Integer, String, Float, Date, DateTime, Boolean,
                        Text, ForeignKey, UniqueConstraint, text)
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
    sort_order = Column(Integer, nullable=False, default=0)  # порядок в списках (drag-n-drop в настройках)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text)
    # Поля для приложения к договору (миграция 2026-09-05_service_doc_fields.sql).
    # Заводятся в конструкторе услуг: одна услуга продаётся одинаково, и держать этот
    # текст в каждой строке медиаплана значило бы переписывать его при каждой сборке.
    # `note` для этого не годится: в соседних справочниках он означает ВНУТРЕННИЙ
    # комментарий, а здесь текст уходит в подписанный клиентом документ.
    doc_position = Column(Text)          # колонка «Позиция» в ДС
    rotation_type = Column(String(20))   # «Динамика» / «Статика»; пусто — формат не медийный
    # Параметры для конструктора МП (см. docs/bridge_deals_operations.md):
    placement_type = Column(String)     # тип размещения: OLV / Banners / Native / … (список на фронте)
    calc_form = Column(String)          # форма расчёта: CPM / CPC / CPV / CPD / Фикс / Пакет (общая)
    separate_price = Column(Boolean, nullable=False, default=False)  # раздельный прайс web/app
    unit_price = Column(Float)          # единая цена/ед (когда separate_price=False)
    unit_price_web = Column(Float)      # цена/ед web (когда separate_price=True)
    unit_price_app = Column(Float)      # цена/ед app (когда separate_price=True)
    # Цвет-маркер услуги (миграция 2026-08-17_service_color.sql): дашборд аккаунта,
    # реестр, МП. NULL = авто по имени из палитры (app/sales/colors.py), а не «нет цвета».
    color = Column(String(7))
    # Базовые константы под форму расчёта (CTR для CPM/CPC, VTR для CPV…): {key: value}.
    # Нужны конструктору МП для производных метрик (показы↔клики и т.п.).
    constants = Column(JSONB)
    # Привязка к услуге в Битриксе (элемент СП 1050 «Продукты Simb-ad»): синк матчит
    # по bx_id, а не по имени, чтобы переименование локальной услуги не рвало связь
    # и не плодило дубли. bx_title — кэш битрикс-имени на момент привязки.
    bx_id = Column(String, index=True)
    bx_title = Column(String)
    # Статья выручки для моста «сделка → операция» (E0): при закрытии сделки операция
    # по этой услуге попадёт в соответствующую статью P&L (группа ВЫРУЧКА). FK на реестр
    # статей финмодуля (app.models.Article). NULL — услуга ещё не сопоставлена.
    revenue_article_id = Column(Integer, ForeignKey("articles.id"))


class SalesAddonService(Base):
    """Доп. услуга (не размещение): фикс-позиция с ценой. can_be_bonus — может идти
    бонусом (при выполнении условий, задаются позже) со скидкой 100%."""
    __tablename__ = "sales_addon_services"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    unit_price = Column(Float)
    period = Column(String)     # период по умолчанию (напр. «первый месяц», «по итогам РК»)
    can_be_bonus = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class SalesFormat(Base):
    """Справочник форматов размещения (Banners / Rich Media / Video / …). Услуга ссылается
    на допустимые форматы через M2M SalesServiceFormat; в строке МП формат выбирается из них.
    group — категория для группировки в выпадашке (Медийка/Видео/Аудио/…)."""
    __tablename__ = "sales_formats"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    group = Column("group", String)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class SalesServiceFormat(Base):
    """M2M услуга ↔ формат. Дефолтный формат услуги хранится строкой в
    SalesService.placement_type (имя формата из числа привязанных) — вариант B."""
    __tablename__ = "sales_service_formats"
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("sales_services.id"), nullable=False)
    format_id = Column(Integer, ForeignKey("sales_formats.id"), nullable=False)
    __table_args__ = (UniqueConstraint("service_id", "format_id", name="uq_service_format"),)


class SalesTargetingItem(Base):
    """Общий каталог значений таргетинга по группам (audience/buys/interests/behavior/
    competitors). Чипы в брифе МП выбираются отсюда; «+добавить» пишет новое значение."""
    __tablename__ = "sales_targeting_items"
    id = Column(Integer, primary_key=True)
    group = Column("group", String, nullable=False)
    value = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("group", "value", name="uq_targeting_group_value"),)


class SalesGeo(Base):
    """Справочник гео для брифа МП."""
    __tablename__ = "sales_geo"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class SalesMediaPlan(Base):
    """Сохранённый медиаплан (шапка). Версии одного МП связаны group_id; в БД держим
    максимум 3 версии на group_id (старейшая удаляется). deal_id — на будущее (привязка
    к сделке пока не пишет в deal.amount). id-поля денормализованы (без FK)."""
    __tablename__ = "sales_media_plans"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft")   # ЗАМОРОЖЕНО 30.08.2026: у всех строк `draft`. Стейт-машины МП нет,
    #                                        состояние плана — стадия его сделки
    title = Column(String)
    advertiser_id = Column(Integer)
    brand_id = Column(Integer)
    agency_id = Column(Integer)
    payer_counterparty_id = Column(Integer)
    period = Column(String)
    geo_id = Column(Integer)
    date_from = Column(Date)
    date_to = Column(Date)
    targeting = Column(JSONB)
    goals = Column(JSONB)
    sales_rep_id = Column(Integer)
    account_manager_id = Column(Integer)
    traffic_manager_id = Column(Integer)
    amount_net = Column(Float)
    amount_gross = Column(Float)
    deal_id = Column(Integer)
    created_by = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    reject_reason = Column(Text)                       # ЗАМОРОЖЕНО 30.08.2026 вместе со статусом
    decided_by = Column(Integer)                       # ЗАМОРОЖЕНО 30.08.2026 вместе со статусом
    decided_at = Column(DateTime(timezone=True))       # когда принято решение


class SalesMediaPlanRow(Base):
    """Строка размещения МП."""
    __tablename__ = "sales_media_plan_rows"
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("sales_media_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    position = Column(String)
    format = Column(String)
    model = Column(String)
    inventory = Column(String)  # 'web' / 'app' / 'cross' — выбор при раздельном прайсе услуги
    volume = Column(Float)
    unit_price = Column(Float)
    discount = Column(Float)
    forecast = Column(JSONB)   # {freq,ctr,cr,price,sov} — ручной ввод прогноза


class SalesMediaPlanExtra(Base):
    """Доп. услуга в МП."""
    __tablename__ = "sales_media_plan_extras"
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("sales_media_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    name = Column(String)
    period = Column(String)
    mode = Column(String)
    price = Column(Float)
    total = Column(Float)


class SalesAdvertiser(Base):
    __tablename__ = "sales_advertisers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # каноничный ключ; = short_name или первое заполненное
    short_name = Column(String)   # короткое — основная колонка в реестре
    name_en = Column(String)
    name_ru = Column(String)
    website = Column(String)
    # NULL намеренно: рекламодатель и плательщик — разные сущности.
    # Пусто = платит агентство, нормальное состояние, а не пропуск данных.
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    inn = Column(String)
    # Ответственный сейлз. NULL — не назначен, нормальное состояние.
    # Профиль из sales_reps (как у сделки и годового плана); ручка принимает id учётки
    # и заводит профиль через ensure_rep. Миграция 2026-09-21_advertiser_sales_rep.sql.
    sales_rep_id = Column(Integer, ForeignKey("sales_reps.id"))
    # перенос листа MP Advertisers — исключение «МП» из выручки
    exclude_from_revenue = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    bx_id = Column(String, nullable=True)   # id компании в Битриксе (заполнит синхрон справочников)
    bx_master = Column(String, nullable=True)  # 'ours' | 'bitrix' — сторона-эталон при связке с Битриксом
    note = Column(Text)
    brands = relationship("SalesBrand", back_populates="advertiser")
    direct_counterparties = relationship("SalesAdvertiserCounterparty", back_populates="advertiser",
                                         cascade="all, delete-orphan")


class SalesBrand(Base):
    __tablename__ = "sales_brands"
    __table_args__ = (UniqueConstraint("advertiser_id", "name"),)
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # Поля маркировки живут на бренде, а не на комплекте креативов: это свойства товара,
    # а не размещения — у одного бренда они не меняются от кампании к кампании.
    # Заполняются один раз и подставляются в каждый комплект, где их можно переопределить.
    # Миграция backend/migrations/2026-08-26_launch_prep_creatives.sql.
    #
    # ККТУ: ровно ОДИН код 3-го уровня вида X.X.X из словаря ОРД (несколько допускаются
    # только для кобрендинга). Без него ЕРИД не выпустить.
    kktu_code = Column(String(16))
    # Общее описание объекта рекламирования, 1–1000 знаков; в ОРД условно-обязательно.
    ad_object_description = Column(Text)
    advertiser = relationship("SalesAdvertiser", back_populates="brands")


class SalesAgency(Base):
    """Рекламное агентство. Отдельная сущность, а не роль контрагента:
    агентство встаёт в разрыв между нами и рекламодателем как плательщик,
    и у него своя иерархия — несколько агентств могут принадлежать одному холдингу.

    counterparty_id nullable: агентство может ещё не иметь договора с нами,
    и тогда юрлица в реестре контрагентов просто нет."""
    __tablename__ = "sales_agencies"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # исходное имя из Битрикса, ключ связи со сделками
    short_name = Column(String)   # краткое — основная колонка в реестре
    name_en = Column(String)
    name_ru = Column(String)
    holding = Column(String)      # необязательно
    is_active = Column(Boolean, nullable=False, default=True)
    sk_percent = Column(Float, nullable=False, server_default="30")  # базовый СК агентства, % (для бонуса сейлза)
    bx_id = Column(String, nullable=True)   # id компании в Битриксе (заполнит синхрон справочников)
    bx_master = Column(String, nullable=True)  # 'ours' | 'bitrix' — сторона-эталон при связке с Битриксом
    note = Column(Text)
    # УСТАРЕЛО: одиночное юрлицо. Заменено связью М:М (несколько юрлиц на агентство).
    # Колонки не удалены (неразрушающе), но через API/UI не читаются.
    legal_entity = Column(String)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    counterparties = relationship("SalesAgencyCounterparty", back_populates="agency",
                                  cascade="all, delete-orphan")


class SalesAgencyCounterparty(Base):
    """Юрлицо агентства. Многие-ко-многим: у одного агентства может быть
    несколько юрлиц (плательщиков), и одно юрлицо теоретически у разных агентств."""
    __tablename__ = "sales_agency_counterparties"
    __table_args__ = (UniqueConstraint("agency_id", "counterparty_id"),)
    id = Column(Integer, primary_key=True)
    agency_id = Column(Integer, ForeignKey("sales_agencies.id", ondelete="CASCADE"), nullable=False)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"), nullable=False)
    agency = relationship("SalesAgency", back_populates="counterparties")


class SalesAdvertiserCounterparty(Base):
    """Юрлицо рекламодателя при прямом договоре. M:M аналог SalesAgencyCounterparty."""
    __tablename__ = "sales_advertiser_counterparties"
    __table_args__ = (UniqueConstraint("advertiser_id", "counterparty_id"),)
    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id", ondelete="CASCADE"), nullable=False)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"), nullable=False)
    advertiser = relationship("SalesAdvertiser", back_populates="direct_counterparties")


class SalesBitrixLink(Base):
    """Связь нашей записи справочника с компанией Битрикса. Много компаний Битрикса
    могут указывать на ОДНУ нашу запись (дубли/юрлица в Битриксе), но одна компания
    Битрикса принадлежит только одной нашей записи (UNIQUE по kind+bx_id).
    kind: 'agencies' | 'advertisers'. our_id — id в sales_agencies/sales_advertisers."""
    __tablename__ = "sales_bitrix_links"
    __table_args__ = (UniqueConstraint("kind", "bx_id", name="uq_bxlink_kind_bxid"),)
    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)
    our_id = Column(Integer, nullable=False)
    bx_id = Column(String, nullable=False)


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
    is_sales_head = Column(Boolean, nullable=False, default=False)  # рук отдела сейлзов — видит дашборды всех
    # Дерево мастеров для эскалаций в уведомлениях (2026-08-15_notifications.sql).
    # Пока не заполнено ни у кого — резолвер master_of_responsible падает на is_sales_head.
    # ВНИМАНИЕ: колонка добавляется миграцией, накатывать её ДО выкладки кода — иначе
    # query(SalesRep) упадёт на проде, ровно как описано ниже про role_group/is_master.
    master_id = Column(Integer, ForeignKey("sales_reps.id"))
    # role_group / is_master были на SalesRep в первой итерации — отменены: рабочая группа
    # для МП живёт на Role (Role.staff_group / is_master). Колонки в БД могли остаться на
    # локали, но НЕ читаются/не пишутся — из модели убраны, чтобы query(SalesRep) не падал
    # на проде, где этих колонок нет (см. предрелизный аудит v2.2.0).


class SalesPipeline(Base):
    __tablename__ = "sales_pipelines"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    # Парсить ли эту воронку из Битрикса. Снятый флаг — воронка не про продажи;
    # синхронизация её пропускает, но существующие данные не трогает.
    # (Физически удалённые воронки СК/Сверка_сайты/БЕЗ СДЕЛКИ здесь не хранятся —
    # флаг для тех, что решили оставить, но временно не учитывать.)
    is_tracked = Column(Boolean, nullable=False, default=True)
    # id воронки в Битриксе (crm.category). Надёжная привязка вместо имени:
    # воронку в портале переименовывают, а id остаётся.
    bitrix_category_id = Column(Integer)
    stages = relationship("SalesPipelineStage", back_populates="pipeline",
                          cascade="all, delete-orphan", order_by="SalesPipelineStage.sort_order")


class SalesPipelineStage(Base):
    """Стадия воронки, как заведена в Битриксе. status_id — код стадии
    («C8:NEW»), по которому API отдаёт сделки; name — человекочитаемое имя.
    Хранится, чтобы справочник показывал состав воронки и чтобы маппинг
    слоёв денег строился по кодам, а не по меняющимся названиям."""
    __tablename__ = "sales_pipeline_stages"
    __table_args__ = (UniqueConstraint("bitrix_category_id", "status_id"),)
    id = Column(Integer, primary_key=True)
    pipeline_id = Column(Integer, ForeignKey("sales_pipelines.id", ondelete="CASCADE"))
    bitrix_category_id = Column(Integer)
    status_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    pipeline = relationship("SalesPipeline", back_populates="stages")


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


# ============ НАШ КАТАЛОГ СТАДИЙ (E1: движение сделки внутри системы) ============
# Собственный, редактируемый каталог стадий, которым владеем МЫ (в отличие от
# хардкода STAGE_CATALOG в stages.py). Стадии сгруппированы по ЭТАПАМ (орг-группировка:
# Песочница / Услуги / ДО …). Каждая стадия несёт разметку 2/2/2 (money_layer — как ДДС
# трактует деньги стадии) и ОДНУ привязку к битрикс воронка+стадия (1:1, чтобы движение
# сделки однозначно толкалось и в Битрикс, пока от него не отказались).

class SalesStagePhase(Base):
    """Этап — орг-группировка наших стадий (Песочница / Услуги / ДО)."""
    __tablename__ = "sales_stage_phases"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    # Этап реализации: его стадии берут воронку Битрикса не из стадии (там только
    # bitrix_status_id), а из выбранной на сделке воронки (deal.realization_pipeline_id).
    # При входе в такой этап диалог движения просит выбрать воронку под продукт.
    is_realization = Column(Boolean, nullable=False, default=False)
    # Сколько сделка может стоять на стадиях этого этапа (дни). Средний уровень каскада
    # SLA: стадия ?? этап ?? дефолт по stage_key (app/sales/urgency.py).
    sla_days = Column(Integer, nullable=True)
    stages = relationship("SalesStage", back_populates="phase",
                          cascade="all, delete-orphan", order_by="SalesStage.sort_order")


class SalesStage(Base):
    """Наша стадия сделки. money_layer — разметка 2/2/2 для ДДС (планируемые/реализуемые/
    фактические; None у терминальных). bitrix_pipeline_id + bitrix_status_id — единственная
    привязка к битрикс воронка+стадия (для синка и толкания сделки обратно в Битрикс)."""
    __tablename__ = "sales_stages"
    id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey("sales_stage_phases.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    # Под-этап 2/2/2 — одна из 6 позиций STAGE_CATALOG (media_plan/booking/launch_prep/
    # launch/closing/archive). Из него выводится money_layer (слой ДДС). None у терминальных.
    stage_key = Column(String)
    money_layer = Column(String)          # производное от stage_key; хранится для джойнов/отчётов
    is_terminal = Column(Boolean, nullable=False, default=False)  # дальше не двигаем
    # Терминальных исходов два, и они разные: положительный («Архив успешных сделок»)
    # и срыв. У срыва stage_key пуст, поэтому без этого флага он неотличим от
    # несопоставленной стадии («требует разбора») — светофор красил бы его серой
    # штриховкой, а очередь звала бы разбирать то, что разбирать не нужно.
    is_lost = Column(Boolean, nullable=False, default=False)
    # Верхний уровень каскада SLA (переопределяет этап). 0 — «здесь срока нет»
    # (терминальные, «В размещении»); NULL — наследовать от этапа.
    sla_days = Column(Integer, nullable=True)
    # Требует привязанный медиаплан для входа (со стадии «МП Отправлено» и далее).
    requires_media_plan = Column(Boolean, nullable=False, default=False)
    bitrix_pipeline_id = Column(Integer, ForeignKey("sales_pipelines.id"))  # наша SalesPipeline.id
    bitrix_status_id = Column(String)     # status_id стадии в этой воронке
    phase = relationship("SalesStagePhase", back_populates="stages")


class SalesStageCheck(Base):
    """Требование к ВХОДУ в стадию. Миграция 2026-09-13_stage_checks.sql.

    `check_key` — имя проверки из реестра в коде, а НЕ имя поля. Иначе на каждый вид
    проверки (колонка сделки, документ, состояние в чужом модуле) код обрастал бы своей
    веткой; с реестром новый случай это строка, а новая порода — функция.

    Адресация входная (владелец 13.09.2026): точнее на развилках, потому что у перехода
    «вперёд» и у перехода «в срыв» требования разные.

    `applies_when` — СДЕЛОЧНАЯ применимость: {"service_id": 7, "self_promo": false}.
    Применимость ПО ПЛОЩАДКАМ сюда не попадает и попасть не может: у одной сделки часть
    площадок с нашим кодом, часть без, и ответа «да/нет» на уровне сделки нет — это
    забота самой веерной проверки.

    Нет строк у стадии = она никого не держит (пустая настройка повторяет прежнее
    поведение)."""
    __tablename__ = "sales_stage_checks"
    __table_args__ = (UniqueConstraint("stage_id", "check_key", name="uq_stage_check"),)
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("sales_stages.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    check_key = Column(String(60), nullable=False)
    # Запирает движение только исход «не сделано». «Неизвестно» (проверить нечем)
    # показывается и пропускает — иначе недостроенный мост заморозил бы конвейер.
    is_blocking = Column(Boolean, nullable=False, default=False)
    applies_when = Column(JSONB)
    sort_order = Column(Integer, nullable=False, default=0)
    hint = Column(Text)


class SalesStageService(Base):
    """Стадия применима к услуге. Нет строк у стадии — применима ко всем.

    Лестница ОДНА на все услуги: от неё кормятся реестр, очередь, годовой план и слои
    денег, и при нескольких лестницах каждый из них спрашивал бы «чья». Применимость
    трогает только движение — неприменимая стадия проскакивается."""
    __tablename__ = "sales_stage_services"
    __table_args__ = (UniqueConstraint("stage_id", "service_id", name="uq_stage_service"),)
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("sales_stages.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("sales_services.id"), nullable=False)


class SalesStageBlock(Base):
    """С какой стадии блок карточки становится виден. Нет строк — виден всегда.

    Два правила, которые таблицей не выражаются и живут в коде:
    · появившийся блок больше НЕ исчезает — иначе движение вперёд прятало бы заполненное;
    · НЕПУСТОЕ НЕ ПРЯЧЕМ НИКОГДА — спрятанные данные не просто невидимы, их невозможно
      найти, и человек заводит их второй раз."""
    __tablename__ = "sales_stage_blocks"
    __table_args__ = (UniqueConstraint("stage_id", "block_key", name="uq_stage_block"),)
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("sales_stages.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    block_key = Column(String(40), nullable=False)   # совпадает с id секции карточки


class SalesDealStageHistory(Base):
    """Каждое движение сделки по нашей лестнице. Миграция 2026-08-17_account_dashboard.sql.

    Две задачи: восстановить «кто и когда двинул» (в Битриксе этого нет — там только
    текущая стадия) и посчитать, сколько сделка реально живёт на каждой стадии, чтобы
    уточнять sla_days по факту, а не по догадке. Вход в стадию = последняя строка
    с этим to_stage_id: от её `at` считается просрочка стадии.

    from_stage_id NULL — первая постановка стадии (импорт из Битрикса или сид)."""
    __tablename__ = "sales_deal_stage_history"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    from_stage_id = Column(Integer, ForeignKey("sales_stages.id"))
    to_stage_id = Column(Integer, ForeignKey("sales_stages.id"), nullable=False)
    user_id = Column(Integer)
    at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(Text)


class SalesDealSnooze(Base):
    """Отложенная сделка: заметка и опциональная дата возврата в очередь.
    Миграция 2026-08-17_account_dashboard.sql.

    Смысл — очередь должна оставаться честной: в ней только то, за что можно взяться
    сегодня. Пока return_at в будущем, строка уходит в свёрнутую группу «Отложено»
    и возвращается сама в указанный день, сохраняя свою срочность.

    return_at NULL — заметка без снятия из очереди (показывается скрепкой).
    Одна запись на сделку (UNIQUE): вторая дата возврата сделала бы неопределённым,
    когда именно сделка вернётся."""
    __tablename__ = "sales_deal_snooze"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"),
                     nullable=False, unique=True)
    note = Column(Text)
    return_at = Column(Date)
    author_id = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())


class SalesDealChecklistState(Base):
    """Отметки чек-листа полноты данных по сделке на конкретной стадии (кто/когда).
    Механизм заложен; наполнение strict/soft-пунктов по стадиям — позже (v1 не блокирует)."""
    __tablename__ = "sales_deal_checklist_state"
    __table_args__ = (UniqueConstraint("deal_id", "stage_id", "item"),)
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id = Column(Integer, ForeignKey("sales_stages.id", ondelete="CASCADE"), nullable=False)
    item = Column(String, nullable=False)
    checked_by = Column(Integer)
    checked_at = Column(DateTime(timezone=True))


# ========================= СДЕЛКИ И ПРИЛОЖЕНИЯ =========================

class AnnexTemplate(Base):
    """Шаблон формулировки услуги в приложении.

    Миграция `backend/migrations/2026-09-05_annex_generator.sql`.

    Привязка к ПЛАТЕЛЬЩИКУ, а не к рекламодателю: подписывает и платит он, у него же свои
    требования к тексту. Бренд приходит подстановкой — в образце «Приложение № 68» это
    «Мезим», а сторона договора — агентство.

    `payer_id = NULL` — типовой шаблон, годный для любого плательщика.
    """
    __tablename__ = "annex_templates"
    id = Column(Integer, primary_key=True)
    payer_id = Column(Integer, ForeignKey("counterparties.id", ondelete="CASCADE"), index=True)
    name = Column(String(200), nullable=False)
    # Подстановки: {бренд} {период_с} {период_по} {сумма} {сумма_прописью}
    # {ндс_ставка} {ндс_сумма} {ндс_сумма_прописью}.
    body = Column(Text, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class SalesAnnex(Base):
    """Приложение к договору. Наше юрлицо не дублируется: выводится из
    `contracts.own_company_id`.

    Поля генератора добавлены миграцией `2026-09-05_annex_generator.sql`.

    **Номер разделён на два поля, и это не дублирование.** `no` — целое, по нему считается
    следующий и держится уникальность внутри договора; `number` — строка, которая
    печатается в документе («Приложение № 68»). Считать по строке нельзя: в живых данных
    номера лежат в шести форматах («1», «доп.1», «прилож. 9»), а печатать надо ровно то,
    что видит клиент.

    Нумерация ведётся ВНУТРИ ДОГОВОРА (владелец 05.09.2026), стартовая точка —
    `Contract.annex_start_no`: почти у всех договоров приложения уже выданы вне системы.
    """
    __tablename__ = "sales_annexes"
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    no = Column(Integer)                 # порядковый внутри договора — для счёта
    number = Column(String)              # как печатается: «Приложение № 68»
    date = Column(Date)                  # последний день предыдущего месяца
    period_from = Column(Date)
    period_to = Column(Date)
    total_amount = Column(Float)
    # Ставка НА МОМЕНТ ПОДПИСАНИЯ: была 20, сейчас 22, однажды поменяется снова.
    # Пересчитывать старое приложение по новой ставке нельзя.
    vat_rate = Column(Float)
    currency = Column(String, nullable=False, default="RUB")
    status = Column(String)
    template_id = Column(Integer, ForeignKey("annex_templates.id"))
    signed_place = Column(String(200))
    created_by = Column(Integer, ForeignKey("users.id"))
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)
    # Документ, ушедший клиенту, остаётся у нас: шаблон поправят, реквизиты сменятся,
    # а подписан был именно этот файл.
    file_path = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())
    items = relationship("SalesAnnexItem", back_populates="annex",
                         cascade="all, delete-orphan")


class SalesDeal(Base):
    """Read-model медиаплана из Битрикс24.

    Слой денег НЕ хранится колонкой: выводится джойном на sales_bitrix_stage_map,
    иначе правка маппинга не влияла бы на уже загруженные сделки."""
    __tablename__ = "sales_deals"
    id = Column(Integer, primary_key=True)
    # Наш 6-значный отпечаток сделки (метка) — стабилен навсегда, показывается в UI и ссылках.
    # bitrix_id ниже НЕ показываем: он несущий ключ синка/надгробий (не путать с code).
    code = Column(String(6), unique=True, index=True)
    bitrix_id = Column(String, nullable=False, unique=True)
    title = Column(String)
    pipeline = Column(String)
    bitrix_stage = Column(String)
    amount = Column(Float)
    amount_with_vat = Column(Float, nullable=True)  # сумма С НДС (клиентская); amount — БЕЗ НДС
    currency = Column(String, nullable=False, default="RUB")
    # Светофор вероятности (наша ручная разметка, не из Битрикса): grey|orange|green|None.
    # Серый — малая вероятность, оранжевый — средняя, зелёный — высокая.
    probability_color = Column(String)
    # E1/E2: движение сделки по НАШЕМУ каталогу стадий.
    # Жёсткий линк на годовой план: сделка принадлежит ячейке плана (строка × месяц).
    # ТОЛЬКО так сделка попадает в план — никакого мягкого матча по advertiser+brand.
    # Сделки, созданные отдельно, в план не входят, пока не прикреплены вручную.
    # План выводится через строку: deal → line.plan_id → SalesYearPlan.
    year_plan_line_id = Column(Integer, ForeignKey("sales_year_plan_lines.id"), nullable=True, index=True)
    plan_month = Column(Integer, nullable=True)                             # 0..11
    # Порядковый номер сделки ВНУТРИ месяца: в конструкторе услуги делятся кнопкой
    # «+ сделка» на группы (products[m][*].deal_idx). Без этого поля повторный прогон
    # конвейера не отличил бы 2-ю сделку месяца от 1-й и плодил бы дубли.
    # Ключ линка: (year_plan_line_id, plan_month, plan_deal_idx). Легаси-сделки — 0.
    plan_deal_idx = Column(Integer, nullable=True, default=0)
    our_stage_id = Column(Integer, ForeignKey("sales_stages.id"))          # текущая стадия у нас
    realization_pipeline_id = Column(Integer, ForeignKey("sales_pipelines.id"))  # выбранная воронка реализации
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"))
    # Одиночная ссылка: один медиаплан — один бренд. Несколько брендов дают
    # несколько медиапланов, сливающихся в одно приложение на «Сборе запуска».
    brand_id = Column(Integer, ForeignKey("sales_brands.id"))
    # Агентство-плательщик. Пусто = прямой договор с рекламодателем.
    agency_id = Column(Integer, ForeignKey("sales_agencies.id"))
    # Плательщик как есть из поля «Компания» Битрикса — агентство при работе
    # через агентство, рекламодатель при прямом договоре. Хранится строкой без
    # интерпретации: связи проставляются только при однозначном совпадении.
    payer_name = Column(String)
    # ЗАМОРОЖЕНО 13.09.2026: сырая строка «Продукты Simb-ad» из Битрикса. Осталась как
    # подпись в старых выгрузках; услугу сделки читать НЕ отсюда — писателей у неё пять
    # и правило «первая строка плана» соблюдал один. Живая услуга — `service_id` ниже.
    product = Column(String)
    # Услуга сделки = первая строка её медиаплана (правило владельца 13.09.2026: одна
    # сделка — одна услуга). Везётся переносом план→сделка, миграция
    # 2026-09-13_deal_service.sql. Ссылка, а не имя: разметка требований сравнивает
    # услугу, и сравнение по имени отключилось бы молча при переименовании в справочнике.
    # NULL — услуга не определена, применяются только общие требования.
    service_id = Column(Integer, ForeignKey("sales_services.id"))
    # Выбранное юрлицо-плательщик (из юрлиц, прикреплённых к агентству сделки).
    # Пусто — берём первое прикреплённое к агентству по умолчанию.
    payer_counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    # Две разные роли, обе из справочника sales_reps и в данных не пересекаются:
    # продавец закреплён за клиентом (колонка CJ), аккаунт-менеджер ведёт сделку
    # со «Сбора запуска» и далее (колонка BI «Ответственный КС»).
    sales_rep_id = Column(Integer, ForeignKey("sales_reps.id"))
    account_manager_id = Column(Integer, ForeignKey("sales_reps.id"))
    # Третий ответственный — трафик-менеджер (backend/migrations/2026-08-26_deal_traffic_manager.sql).
    # Тот же ростер, что у sales_rep_id/account_manager_id (sales_reps, не users) — резолвится
    # в routers/sales_dashboard.py тем же способом, что и account_manager_id.
    traffic_manager_id = Column(Integer, ForeignKey("sales_reps.id"))
    # Продление: какую кампанию скопировали (2026-08-28_publisher_requests.sql).
    # Без родословной «эта РК — продление той» знает только человек. Исходная сделка при
    # этом живёт своей жизнью в рамках стадий — копия это экономия времени, а не перевод
    # старой кампании в особое состояние.
    prolonged_from_id = Column(Integer, ForeignKey("sales_deals.id"))
    # Самореклама: у неё в ОРД свой тип договора и обязательный флаг isSelfPromotion
    # при выпуске креатива. На 26.08.2026 признак только помечает сделку — отдельная
    # цепочка под саморекламу будет расписана позже.
    is_self_promo = Column(Boolean, nullable=False, server_default='false')
    annex_id = Column(Integer, ForeignKey("sales_annexes.id"))
    # Изначальный договор ОРД, которым закрывали сборку по этой сделке — единственная
    # память о прошлом выборе для пары агентство×рекламодатель (app/ord/matching.py,
    # _last_used_initial). Колонка добавлена в БД миграцией
    # backend/migrations/2026-08-25_ord_mirror.sql (ALTER TABLE sales_deals ...) —
    # здесь только маппинг, ALTER в этом файле не выполняется.
    ord_initial_contract_id = Column(Integer, ForeignKey("ord_initial_contracts.id"))
    # Доходный договор, выбранный человеком на ступени сборки. Пусто — работает
    # вычисление от плательщика (app/ord/matching.py, resolve_final), и экран показывает
    # его как подсказку; заполнено — выбор побеждает. Тот же узор, что строкой выше.
    # Миграция backend/migrations/2026-08-26_deal_ord_final_contract.sql.
    ord_final_contract_id = Column(Integer, ForeignKey("contracts.id"))
    date_create = Column(DateTime)
    date_modify = Column(DateTime)
    # Период размещения — «Старт РК» / «Конец РК». Основная ось витрины:
    # дата создания сделки для отчётности бесполезна, деньги относятся
    # к периоду размещения. period_to = NULL — календарный месяц period_from.
    period_from = Column(Date)
    period_to = Column(Date)
    synced_at = Column(DateTime, server_default=func.now())
    # Бриф — Битрикс-поле ufCrm_1761318500 «Бриф - Описание задач». Ленивая подгрузка:
    # NULL = ещё не тянули из Битрикса; после первого открытия кэшируется здесь.
    # Правка двусторонняя: сохраняем сюда и патчим в Битрикс. brief_synced_at — момент
    # последней синхронизации с Битриксом (подтяжки или записи).
    brief = Column(Text, nullable=True)
    brief_synced_at = Column(DateTime, nullable=True)
    # «Цели и особенности РК» — передача задачи от аккаунта трафику
    # (backend/migrations/2026-09-05_deal_traffic_brief.sql). Отдельно от `brief`
    # СОЗНАТЕЛЬНО: бриф ездит в Битрикс в обе стороны, а это внутренний текст, снаружи
    # его быть не должно. Кто и когда правил — в журнале действий, своих колонок
    # «кем/когда» нет намеренно: вторая память о том же событии разойдётся с первой.
    traffic_brief = Column(Text, nullable=True)
    # Доп. параметры РК (миграция 2026-09-14_deal_weborama_pixel.sql). Первый и пока
    # единственный: нужен ли по этой РК пиксель верификатора. Не пометка для трафика —
    # от него зависит, потребует ли выгрузка в DSP пикселя (`dsp/provision._blocker`) и
    # появится ли проверка стадии `weborama_pixel`. Включает аккаунт, снимает мастер.
    weborama_pixel = Column(Boolean, nullable=False, server_default=text("false"),
                            default=False)
    weborama_pixel_at = Column(DateTime, nullable=True)
    # КОГДА РЕШИЛИ — отдельно от того, ЧТО решили (миграция 2026-09-18_pixel_decision).
    # Пусто означает «выбор ещё не сделан»: блок доп. параметров РК на карточке стоит
    # развёрнутым, пока человек не нажал «надо» или «не надо». Булев флаг рядом этого
    # различить не мог — «не надо» и «не решали» были в нём одним значением.
    weborama_pixel_decided_at = Column(DateTime, nullable=True)
    # Откуда берётся пиксель (миграция 2026-09-14_weborama_external_pixel.sql):
    # own — заводим вставку и забираем пиксель сами; external — тег принесли готовым,
    # ОДИН на всю кампанию (у них одна вставка на сеть). Осмысленно только при
    # включённом `weborama_pixel`.
    weborama_pixel_mode = Column(String(10), nullable=False,
                                 server_default=text("'own'"), default="own")
    weborama_pixel_tag = Column(Text, nullable=True)
    weborama_ext_insertion = Column(String(32), nullable=True)
    # Светофор синхронизации (считается при sync_deal_from_bitrix):
    # green — совпадает с Битриксом; blue — у нас данные полнее (не выгружено);
    # red — расхождение (Битрикс не матчится с нашими справочниками). NULL — не проверялось.
    sync_status = Column(String, nullable=True)
    sync_checked_at = Column(DateTime, nullable=True)
    sync_report = Column(JSONB, nullable=True)   # {issues:[{field,message}], changes:[...], checked_at}


class SalesDealFieldOverride(Base):
    """Поле сделки, заполненное человеком у нас, а не пришедшее из Битрикса.

    Три задачи одной таблицей:
    1. Синхронизация не затирает ручной ввод — поле со строкой правки не трогается.
       Тот же принцип, что у контрагентов в финмодуле («ручной ввод никогда
       не перезатирается», см. docs/INTEGRATION_SPEC.md раздел 3.1).
    2. Видно авторство и время правки.
    3. Заливка в Битрикс берёт строки с pushed_at IS NULL — сравнивать ничего
       не нужно, задвоить отправку нельзя.

    Значение дублируется в саму sales_deals, чтобы реестр и витрина работали
    обычными запросами без джойна на правки.

    Удаление строки правки возвращает поле под управление синхронизации —
    это и есть механизм отката."""
    __tablename__ = "sales_deal_field_overrides"
    __table_args__ = (UniqueConstraint("deal_id", "field_name"),)
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String, nullable=False)
    value_int = Column(Integer)    # для ссылок: advertiser_id, brand_id, sales_rep_id...
    value_text = Column(String)    # для дат и строк: period_from, period_to
    set_by = Column(Integer, ForeignKey("users.id"))
    set_at = Column(DateTime, server_default=func.now())
    pushed_at = Column(DateTime)   # NULL = в Битрикс ещё не отправлено


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


class SalesDeletedDeal(Base):
    """Надгробие удалённой сделки. Синхронизация с Битриксом ОБЯЗАНА пропускать
    сделки, чей bitrix_id здесь: иначе удалённые вручную сделки воскреснут
    при первом же прогоне, т.к. в Битриксе они ещё существуют."""
    __tablename__ = "sales_deleted_deals"
    id = Column(Integer, primary_key=True)
    bitrix_id = Column(String, nullable=False, unique=True)
    reason = Column(String)
    deleted_at = Column(DateTime, server_default=func.now())
    deleted_by = Column(Integer, ForeignKey("users.id"))


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


class SalesDealComment(Base):
    """Комментарий на карточке сделки — лента, а не поле.

    Таблица создаётся миграцией backend/migrations/2026-09-05_deal_comments.sql.

    Правок и удалений нет намеренно (владелец 05.09.2026): «каждый новый отдельной
    записью» — это свидетельство о том, кто что и когда сказал, а редактируемая лента
    свидетельством быть перестаёт.

    Автор — УЧЁТКА, а не профиль ответственного: профиля нет у половины сотрудников, он
    заводится только при назначении (app/sales/reps.py), и комментарий человека без
    профиля остался бы без автора.
    """
    __tablename__ = "sales_deal_comments"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class SalesDealFile(Base):
    """Файл сделки (МП / договор), скачанный из Битрикса и сохранённый у нас
    в персистентном томе /app/uploads. Живой URL Битрикса временный — поэтому
    держим копию и отдаём её сами."""
    __tablename__ = "sales_deal_files"
    __table_args__ = (UniqueConstraint("deal_id", "kind"),)
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String, nullable=False)            # 'mp' | 'contract'
    bitrix_file_id = Column(String)
    filename = Column(String)
    path = Column(String, nullable=False)            # относительный путь внутри /app/uploads
    size = Column(Integer)
    content_type = Column(String)
    synced_at = Column(DateTime, server_default=func.now())


class SalesYearPlan(Base):
    """План/пакет годового планирования = группировка под задачу.

    Один рекламодатель может иметь НЕСКОЛЬКО планов за год (разные агентства /
    номенклатуры брендов = независимые планы). title различает их для человека
    (автоген по умолчанию + ручная правка, как заголовок сделки). Строки-бренды
    (SalesYearPlanLine) принадлежат плану через plan_id; сделки — через строку.
    """
    __tablename__ = "sales_year_plans"
    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"), nullable=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    title = Column(String)                                       # редактируемый заголовок
    account_manager_id = Column(Integer, ForeignKey("sales_reps.id"), nullable=True)  # аккаунт-создатель (мастер может сменить)
    sales_rep_id = Column(Integer, ForeignKey("sales_reps.id"), nullable=True, index=True)  # в чей дашборд по умолчанию
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SalesYearPlanLine(Base):
    """Строка годового плана: один рекламодатель × один бренд × год.
    Факт/бронь НЕ хранятся вычислением — по кнопке «Обновить данные о сделках»
    метчатся реальные сделки и результат замораживается в `deals` (статика).

    JSON-карты ключуются строковым индексом месяца '0'..'11' (JSON-объект не имеет
    целочисленных ключей). Фронт нормализует обратно в числа.
    """
    __tablename__ = "sales_year_plan_lines"
    id = Column(Integer, primary_key=True)
    # Родитель — план/пакет. NULL только у легаси-строк до бэкфилла.
    plan_id = Column(Integer, ForeignKey("sales_year_plans.id"), nullable=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    # ДВЕ ОСИ ВЛАДЕНИЯ, и путать их нельзя: sales_rep_id — ПРОДАВЕЦ, в чей дашборд
    # считаются деньги строки; account_manager_id — тот, кто план ВЕДЁТ. Строку видит
    # и тот, и другой.
    #
    # До 21.09.2026 ось была одна, и в неё писался создатель. Годовые планы заводят и
    # аккаунты — такой план уходил в персональную корзину аккаунта: продавец его не
    # видел, руководитель не видел, деньги считались не туда. Оба значения человек
    # уже вводит в брифе строки, они просто ни на что не влияли.
    # Миграция 2026-09-21_year_plan_account_manager.sql.
    sales_rep_id = Column(Integer, ForeignKey("sales_reps.id"), nullable=True, index=True)
    account_manager_id = Column(Integer, ForeignKey("sales_reps.id"), nullable=True, index=True)
    # nullable — легальный черновик: строка без выбранного рекламодателя/бренда.
    advertiser_id = Column(Integer, ForeignKey("sales_advertisers.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("sales_brands.id"), nullable=True)
    plan_amount = Column(Float, nullable=False, default=0)
    months_on = Column(JSONB, nullable=False, default=list)     # [0|1]×12
    sums = Column(JSONB, nullable=False, default=dict)          # {"m": сумма руками}
    locks = Column(JSONB, nullable=False, default=dict)         # {"m": 1}
    # {"m": [{ref_id, type:'service'|'addon', amount, units}, ...]} — помесячно, сумма+объём
    # закупки на услугу. Есть услуги в месяце → sums[m] = Σ amount (фронт).
    products = Column(JSONB, nullable=False, default=dict)
    deals = Column(JSONB, nullable=False, default=dict)         # {"m": [[bx_id, amount, closed],...]}
    # Бриф строки-бренда (одна на строку): {agency_id, payer_counterparty_id, geo_id,
    # targeting{audience,buys,interests,behavior,competitors}, sales_rep_id,
    # account_manager_id, text}. Повторяет бриф конструктора МП без блока медиаплана.
    brief = Column(JSONB, nullable=False, default=dict)
    # Прогноз на услугу ЗА ГОД: {"<type>:<ref_id>": {freq,ctr,cr,price,sov,volume}}.
    # Поля ввода как в МП; считается на суммарные деньги+units услуги по всем месяцам.
    service_forecast = Column(JSONB, nullable=False, default=dict)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


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


# ============================ ПАБЛИШЕРЫ ============================
# Таблицы создаются миграцией backend/migrations/2026-08-19_publishers.sql.

PUBLISHER_STATUSES = ["ПЕРЕГОВОРЫ", "СОТРУДНИЧАЕМ", "НА ПАУЗЕ", "ОТКАЗ", "АРХИВ"]
# Отсутствие строки поверхности значит то же, что «НЕТ»: поверхности нет и разговора
# о ней не было. Отдельного значения под «не обсуждали» нет намеренно — в исходной
# таблице оно и «ОТСТУТСТВУЕТ» стояли вперемешку об одном и том же.
SURFACE_STATUSES = ["НЕТ", "ОТЛОЖЕНО", "ПОДГОТОВКА", "СОГЛАСОВАНИЕ", "ПРАВКИ", "ПОДКЛЮЧЕНО"]
SURFACE_KINDS = ["web", "app"]
PLATFORM_KINDS = ["android", "ios"]
# Ровно четыре строки таблицы трафика в интерфейсе.
TRAFFIC_SCOPES = ["web", "app_android", "app_ios", "ad_requests"]
PUBLISHER_DEAL_TYPES = ["прямой", "посредник"]
SELF_PROMO_VALUES = ["ДА", "НЕТ", "ЗАПРОСИТЬ"]
PUBLISHER_CONTRACT_ROLES = ["с площадкой", "агентский"]


def normalize_domain(value):
    """Ключ площадки. Регистр и пробелы по краям съедают сравнение: в исходной
    таблице один сайт писали как «ETABL.RU », «ASNA.ru» и «Farmlend.ru»."""
    return (value or "").strip().lower().rstrip("/")


class SalesPublisherKind(Base):
    """Вид паблишера. Не раздел меню, а накопитель значений: введённое в карточке имя
    сохраняется и дальше предлагается в выпадашке — так же, как чипы таргетинга."""
    __tablename__ = "sales_publisher_kinds"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)


# Статус архива площадки. `is_active` для этого НЕ годится: у архивных он тоже true —
# признак живёт в `status`. Архивные игнорируются в админке трафика (решение владельца
# 02.09.2026): ни в балансировщике, ни в каталоге блоков, ни при импорте блоков.
PUBLISHER_ARCHIVE_STATUS = "АРХИВ"


class SalesPublisher(Base):
    """Площадка. Веб и приложение вынесены в SalesPublisherSurface: юрлицо, договор,
    чат и контакты у сайта одни, а фигма, статус интеграции и покрытие мест — свои
    у каждой поверхности."""
    __tablename__ = "sales_publishers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=False, unique=True)  # хранится нормализованным
    # Постоянный короткий код площадки (MKS, DPD) — средняя часть кода пары
    # «креатив × площадка» вида HCLA6E-MKS-01, по которому пара учитывается в DSP.
    # Не меняется никогда: код уже уехавшего размещения переименовать нельзя.
    # Миграция backend/migrations/2026-08-26_launch_prep_creatives.sql.
    code = Column(String(8), unique=True)
    kind = Column(String)      # имя из sales_publisher_kinds, не FK
    status = Column(String, nullable=False, default="ПЕРЕГОВОРЫ")
    network = Column(String)   # NULL = независимая, а не сеть с именем «НЕЗАВИСИМЫЕ»
    deal_type = Column(String)
    intermediary_counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    is_exclusive = Column(Boolean, nullable=False, default=False)
    has_dsp = Column(Boolean, nullable=False, default=False)
    # Отметка для справки. НЕ вычисляется из статусов поверхностей: вычисляемая и
    # проставленная руками правда об одном и том же неизбежно расходятся.
    our_code = Column(Boolean, nullable=False, default=False)
    # Делится ли площадка данными — меняет механики Альфарм-Таргета (тег DATA/NO DATA).
    shares_data = Column(Boolean, nullable=False, default=False)
    # Смещение от МСК в часах: звонок в 8 утра по Москве во владивостокскую аптеку
    # приходится на конец их рабочего дня.
    timezone_offset = Column(Integer, nullable=False, default=0)
    tech_requirements = Column(Text)
    media_kit_filename = Column(String)
    media_kit_path = Column(String)
    media_kit_uploaded_at = Column(DateTime)
    # УСТАРЕЛО с 2026-08-19: приоритезация ведётся услугой каталога (sales_services),
    # а не признаком площадки. Колонка заморожена, код её не читает.
    is_priority = Column(Boolean, nullable=False, default=False)
    self_promo = Column(String)
    self_promo_note = Column(Text)
    cpm_contract = Column(Float)   # закупочный CPM до НДС по договору
    basket_note = Column(Text)
    note = Column(Text)
    chat_title = Column(String)
    chat_url = Column(String)      # телеграм; ссылки нет у части чатов — известно только название
    chat_url_max = Column(String)  # MAX: часть площадок уходит с телеграма, период двух чатов уже идёт
    messenger_note = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    surfaces = relationship("SalesPublisherSurface", back_populates="publisher",
                            cascade="all, delete-orphan")
    services = relationship("SalesPublisherService", back_populates="publisher",
                            cascade="all, delete-orphan")
    counterparties = relationship("SalesPublisherCounterparty", back_populates="publisher",
                                  cascade="all, delete-orphan")
    contracts = relationship("SalesPublisherContract", back_populates="publisher",
                             cascade="all, delete-orphan")
    contacts = relationship("SalesPublisherContact", back_populates="publisher",
                            cascade="all, delete-orphan")
    traffic = relationship("SalesPublisherTraffic", cascade="all, delete-orphan")
    documents = relationship("SalesPublisherDocument", cascade="all, delete-orphan")


class SalesPublisherSurface(Base):
    __tablename__ = "sales_publisher_surfaces"
    __table_args__ = (UniqueConstraint("publisher_id", "kind", name="uq_publisher_surface"),)
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    kind = Column(String, nullable=False)   # web | app
    figma_url = Column(String)
    # МС-реквизиты DSP на поверхность (миграция 2026-09-01_traffic_catalog.sql): id паблишера
    # в DSP и блок по умолчанию «кукуха2» (авто-цепляется к креативу, скрыт из
    # статистики кабинета). На каждую web/app — свои; ios/android (платформы) — на будущее.
    ms_publisher_id = Column(String)
    default_ms_block_id = Column(String)
    integration_status = Column(String, nullable=False, default="НЕТ")
    # Наличие строки отвечает «поверхность у площадки есть», флаг — «мы с ней работаем».
    # Раньше это было склеено в статусе, и «приложения нет» не отличалось от
    # «приложение есть, но мы его не продаём».
    we_work = Column(Boolean, nullable=False, default=False)
    coverage_percent = Column(Float)
    note = Column(Text)
    publisher = relationship("SalesPublisher", back_populates="surfaces")
    platforms = relationship("SalesPublisherSurfacePlatform", back_populates="surface",
                             cascade="all, delete-orphan")


class SalesPublisherSurfacePlatform(Base):
    """Платформа приложения. APP не монолит: Android бывает подключён, когда iOS ещё
    в подготовке. Услуги отмечаются на поверхности (прайс общий), а трафик считается
    по платформам отдельно — иначе закупку не спланировать."""
    __tablename__ = "sales_publisher_surface_platforms"
    __table_args__ = (UniqueConstraint("surface_id", "kind", name="uq_surface_platform"),)
    id = Column(Integer, primary_key=True)
    surface_id = Column(Integer, ForeignKey("sales_publisher_surfaces.id", ondelete="CASCADE"),
                        nullable=False)
    kind = Column(String, nullable=False)   # android | ios
    integration_status = Column(String, nullable=False, default="НЕТ")
    is_active = Column(Boolean, nullable=False, default=False)
    note = Column(Text)
    surface = relationship("SalesPublisherSurface", back_populates="platforms")


class SalesPublisherTraffic(Base):
    """Замер трафика на месяц, а не поле карточки: в исходной таблице цифры записаны
    текстом вперемешку («900 тыс», «2,05 млн») и относятся к конкретному периоду.
    Повторный ввод за тот же месяц исправляет замер, а не добавляет вторую точку."""
    __tablename__ = "sales_publisher_traffic"
    __table_args__ = (UniqueConstraint("publisher_id", "scope", "measured_at",
                                       name="uq_publisher_traffic"),)
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    scope = Column(String, nullable=False)   # web | app_android | app_ios | ad_requests
    value = Column(Float)
    depth = Column(Float)   # глубина просмотра; у запросов рекламного кода её нет
    measured_at = Column(Date, nullable=False)   # первое число месяца
    source = Column(String, nullable=False, default="manual")


class SalesPublisherService(Base):
    """Услуга, поддерживаемая площадкой, на конкретной поверхности: у услуг с
    раздельным прайсом web и app — разные тарифы и разная готовность."""
    __tablename__ = "sales_publisher_services"
    __table_args__ = (UniqueConstraint("publisher_id", "surface_kind", "service_id",
                                       name="uq_publisher_service"),)
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    surface_kind = Column(String, nullable=False)
    service_id = Column(Integer, ForeignKey("sales_services.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text)
    publisher = relationship("SalesPublisher", back_populates="services")


class SalesPublisherCounterparty(Base):
    """Юрлицо площадки. М:М: одно юрлицо (ДПД Медиа) стоит за двумя десятками площадок."""
    __tablename__ = "sales_publisher_counterparties"
    __table_args__ = (UniqueConstraint("publisher_id", "counterparty_id",
                                       name="uq_publisher_counterparty"),)
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"), nullable=False)
    publisher = relationship("SalesPublisher", back_populates="counterparties")


class SalesPublisherContract(Base):
    __tablename__ = "sales_publisher_contracts"
    __table_args__ = (UniqueConstraint("publisher_id", "contract_id", "role",
                                       name="uq_publisher_contract"),)
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    # NULL: договор известен номером, но в реестре «Договора» его пока нет — там лежат
    # договоры с клиентами, а не с площадками. Ссылка проставится к этому же ряду.
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    number_raw = Column(String)
    role = Column(String, nullable=False, default="с площадкой")
    # Договор не удаляют: по нему шли деньги. Архив прячет его из карточки, оставляя
    # запись и связь целыми.
    is_archived = Column(Boolean, nullable=False, default=False)
    # Куда ведёт кнопка рядом с номером: файл в системе или ссылка на ЭДО.
    document_source = Column(String)   # file | edo
    document_url = Column(String)
    document_filename = Column(String)
    document_path = Column(String)
    publisher = relationship("SalesPublisher", back_populates="contracts")


class SalesDocumentType(Base):
    """Каталог типов документов площадки: «Медиакит», «ТТ на баннеры»,
    «Доп. инструкции». Пополняется вводом из формы загрузки — так же, как должности
    контактов и виды паблишеров."""
    __tablename__ = "sales_document_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)


class SalesPublisherDocument(Base):
    """Файл площадки. Медиакит — один из типов, а не отдельное поле: иначе каждый
    новый вид документа требовал бы своей тройки колонок в sales_publishers."""
    __tablename__ = "sales_publisher_documents"
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    doc_type = Column(String, nullable=False)   # имя из sales_document_types, не FK
    filename = Column(String, nullable=False)   # имя на диске, с префиксом id
    path = Column(String)
    uploaded_at = Column(DateTime, server_default=func.now())
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    note = Column(Text)


class SalesDealBriefFile(Base):
    """Файл, приложенный к брифу сделки (миграция 2026-09-21_deal_brief_files.sql).

    Бриф приходит от клиента не только текстом — презентацией, тз, чужим медиапланом.
    Своя таблица, а не тройка колонок на сделке: файлов бывает несколько, и одна колонка
    молча затирала бы первый вторым. Тот же довод, что у `SalesPublisherDocument`.

    `filename` — имя на диске в `/app/uploads/deal_briefs/` (с префиксом id, иначе два
    «бриф.pdf» затрут друг друга); `original_name` — под ним файл отдаётся человеку.
    """
    __tablename__ = "sales_deal_brief_files"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    size_bytes = Column(Integer)
    uploaded_at = Column(DateTime, server_default=func.now())
    uploaded_by = Column(Integer, ForeignKey("users.id"))


class SalesContactPosition(Base):
    """Общий каталог должностей контактных лиц (миграция 2026-08-19_contact_positions.sql).
    Каталог один на всех: «аккаунт» и «бухгалтерия» повторяются у каждой площадки, а
    свободный ввод через месяц даёт три написания одной должности. Связь справочная,
    не FK: переименование должности не должно осиротить контакт."""
    __tablename__ = "sales_contact_positions"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)


class SalesPublisherContact(Base):
    __tablename__ = "sales_publisher_contacts"
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False)
    name = Column(String)
    email = Column(String)
    telegram = Column(String)
    phone = Column(String)
    role = Column(String)          # должность
    is_primary = Column(Boolean, nullable=False, default=False)
    max_url = Column(String)       # MAX равноправен телеграму: площадки уходят с ТГ
    # Получает ли контакт уведомления кабинета (миграция 2026-09-14_contact_notify.sql).
    # Отдельно от `is_primary`: тот отвечает «к кому идти с вопросом», а это — «кому
    # уходит почта». Совпадали они по случайности и разошлись бы на первом же «главный,
    # но писать ему не надо».
    notify = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    note = Column(Text)
    publisher = relationship("SalesPublisher", back_populates="contacts")
