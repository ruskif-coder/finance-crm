"""ORM модуля «Дашборд трафика» — рекламные кампании (РК) в DSP.

Таблицы создаёт миграция `migrations/2026-09-01_ad_campaigns.sql` (согласовано
владельцем 01.09.2026, спека `docs/SPEC_дашборд_трафика.md`). Здесь только маппинг —
`create_all` дозаведёт их на свежей базе, но источник истины по схеме — миграция.

Грань: 1 РК = 1 сделка (`AdCampaign.deal_id` unique); распределение объёма — на площадке
(`AdCampaignPlacement`), сам креатив в МС — на связке площадка×креатив
(`AdCampaignCreative`, у каждого свой ЕРИД и сквозное имя). Веса площадок НЕ дублируются —
берутся из `sales_publisher_traffics`; комплект/файлы/пары — из `launch_prep_*`.
"""
from sqlalchemy import (Boolean, Column, Date, DateTime, Float,
                        ForeignKey, Integer, String, Text, UniqueConstraint, func)

from app.database import Base


class AdCampaign(Base):
    """РК — одна на сделку. `set_id` NULL, пока сделка «ожидает сборки»."""
    __tablename__ = "ad_campaign"

    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"),
                     nullable=False, unique=True)
    set_id = Column(Integer, ForeignKey("launch_prep_creative_set.id", ondelete="SET NULL"))
    month = Column(Date)                       # 1-е число месяца РК
    status = Column(String(32), nullable=False, default="ожидает сборки")
    date_start = Column(Date)
    date_end = Column(Date)
    plan_show = Column(Float)        # = лимиты кампании в МС
    plan_click = Column(Float)
    plan_budget = Column(Float)
    ms_campaign_xxhash = Column(String(64))    # id кампании в DSP
    ms_synced_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(),
                        onupdate=func.now())


class AdCampaignPlacement(Base):
    """Площадка внутри РК = source в МС. Уровень распределения объёма."""
    __tablename__ = "ad_campaign_placement"
    __table_args__ = (UniqueConstraint("campaign_id", "publisher_id"),)

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("ad_campaign.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id"), nullable=False)
    ms_source_key = Column(String(64))         # x-simb-web / x-simb + блок
    weight = Column(Float)           # снимок из sales_publisher_traffics
    share = Column(Float)            # доля %, пересчёт при выпадении
    plan_show = Column(Float)
    daily_limit_plan = Column(Float)  # суточный ОРИЕНТИР (день-в-день — МС uniform_pro)
    bid = Column(Float)              # ставка source — наш рычаг
    # Шесть значений — `app/ad/flight.PLACEMENT_STATUSES`. Первые три ставит конвейер
    # согласования, последние три выбирает трафик (миграция 2026-09-04_placement_statuses).
    # Умолчание — «ждёт сборки»: площадка попадает в РК кандидатом, когда креативов по
    # ней ещё нет вовсе (миграция 2026-09-18_placement_wait_status.sql).
    status = Column(String(32), nullable=False, default="ждёт сборки")
    is_direct = Column(Boolean, nullable=False, default=False)   # «крутит сама» (10%)
    # Сырой пиксель показа Weborama (`a.A=im`), как пришёл: с `[RANDOM]`, `~WIDTH~`,
    # `${GDPR}`. Итоговый тег НЕ храним — он производный и зависит от того, куда едет
    # (макрос рандомизатора у DSP и Adfox разный) и от размера конкретного креатива.
    # Хранить производное значит завести вторую правду, которая разойдётся с первой.
    # Миграция 2026-09-09_weborama.sql.
    weborama_pixel = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(),
                        onupdate=func.now())


class AdCampaignCreative(Base):
    """Креатив в МС: связка площадка×креатив. Сквозное имя, свой ЕРИД.

    Зерно — РЕКЛАМНОЕ СООБЩЕНИЕ на площадке, а не версия комплекта (владелец 04.09.2026:
    «креатив как рекламное сообщение един, а правки обычно технические»). Отсюда две
    связи, добавленные миграцией `2026-09-04_ad_creative_links.sql`:

      · `root_set_id` — корень цепочки доработок, ЛИЧНОСТЬ сообщения. По нему же строится
        обратный вид «креатив → площадки»;
      · `pair_id` — ТЕКУЩАЯ пара согласования. Доработка рождает новую пару, ссылка
        переставляется, а строка остаётся — вместе с ЕРИД и хешом МС.

    Уникальность `(placement_id, root_set_id)`: одно сообщение на одной площадке. Без неё
    доработка плодила бы вторую строку, и счётчик «всего» рос бы с каждой правкой.
    """
    __tablename__ = "ad_campaign_creative"
    __table_args__ = (UniqueConstraint("placement_id", "creative_no"),)

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("ad_campaign.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    placement_id = Column(Integer, ForeignKey("ad_campaign_placement.id", ondelete="CASCADE"),
                          nullable=False)
    file_id = Column(Integer, ForeignKey("launch_prep_creative_file.id", ondelete="SET NULL"))
    creative_no = Column(Integer, nullable=False)   # cr№
    ms_creative_xxhash = Column(String(64))
    erid = Column(String(64))                  # свой на связку
    # Сквозное имя: <deal.code>-<publisher.code>-cr<no> (по нашему коду — решение владельца;
    # переключатель code|dsp в company_settings.dsp_name_publisher_ref). Собирается кодом.
    ms_title = Column(String(255))
    # Корень цепочки доработок и текущая пара — см. докстринг класса.
    root_set_id = Column(Integer, ForeignKey("launch_prep_creative_set.id"))
    pair_id = Column(Integer, ForeignKey("launch_prep_pair.id", ondelete="SET NULL"))
    # Словарь из шести значений — `app/ad/flight.CREATIVE_STATUSES`. «Создан» из него
    # убран: свежая строка означает «материал у трафика», а не «непонятно где».
    status = Column(String(32), nullable=False, default="у трафика",
                    server_default="у трафика")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(),
                        onupdate=func.now())


class PublisherBlock(Base):
    """Каталог рекламных блоков площадки (импорт из «Площадки и блоки.xlsx»).

    Вешается на существующую поверхность площадки `sales_publisher_surfaces` (web/app) —
    отдельной таблицы под поверхности НЕ заводим, переиспользуем модуль паблишеров
    (миграция `2026-09-01_traffic_catalog.sql`). МС-реквизиты поверхности (`ms_publisher_id`,
    `default_ms_block_id`/«кукуха2») лежат на самой `sales_publisher_surfaces`. Старые
    колонки `publisher_id`/`surface`/`network` — денормализованные, заполняются импортёром;
    источник истины по принадлежности — `surface_id`.
    """
    __tablename__ = "publisher_block"
    __table_args__ = (UniqueConstraint("surface_id", "ms_block_id", name="uq_block_surface_msid"),)

    id = Column(Integer, primary_key=True)
    surface_id = Column(Integer, ForeignKey("sales_publisher_surfaces.id", ondelete="CASCADE"),
                        index=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False, index=True)   # денорм
    surface = Column(String(8))                # денорм: web | app
    ms_block_id = Column(String(64))
    name = Column(String(255))                 # название в xoalt (cart / aboveReco)
    page_type = Column(String(64))             # раздел: главная/каталог/карточка/корзина/статьи/акции/лк
    network = Column(String(32))               # x-simb-web / x-simb (МС source-ключ)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AdCampaignStat(Base):
    """Факт показов/кликов из stat-API МС. `placement_id` NULL — если API без разреза."""
    __tablename__ = "ad_campaign_stat"
    # NULLS NOT DISTINCT в миграции — SQLAlchemy до 2.1 его не декларирует; уникум держит БД.
    __table_args__ = (UniqueConstraint("campaign_id", "placement_id", "date", "source",
                                       name="uq_ad_stat"),)

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("ad_campaign.id", ondelete="CASCADE"),
                         nullable=False)
    placement_id = Column(Integer, ForeignKey("ad_campaign_placement.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    shows = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    source = Column(String(16), nullable=False, default="ms")   # ms | manual
    imported_at = Column(DateTime, nullable=False, server_default=func.now())

class PublisherBalanceIndex(Base):
    """Балансировщик: расчётная ёмкость площадки НА ПОВЕРХНОСТЬ (показов/мес).

    Миграция `2026-09-02_balance_index.sql`. Зерно `(площадка × scope)` зеркалит
    `sales_publisher_traffic.scope` (web / app_android / app_ios) — веса web и app правятся
    отдельно. Индекс АБСОЛЮТНЫЙ: доля считается внутри РК от участников
    (`ad_campaign_placement.weight` → `share`), поэтому выпадение площадки не трогает индексы.

    Действующий индекс = `COALESCE(index_manual, index_auto)`; `is_locked` защищает ручную
    правку от пересчёта, `source` показывает, чем посчитан auto (замер / оценка / рука).
    """
    __tablename__ = "publisher_balance_index"
    __table_args__ = (UniqueConstraint("publisher_id", "scope"),)

    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    scope = Column(String(16), nullable=False)      # web | app_android | app_ios
    index_auto = Column(Float)                      # пересчёт формулой
    index_manual = Column(Float)                    # правка рукой; NULL = не правили
    is_locked = Column(Boolean, nullable=False, default=False)
    source = Column(String(16))                     # ad_requests | estimate | manual
    note = Column(Text)
    calculated_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))

    @property
    def effective(self):
        return self.index_manual if self.index_manual is not None else self.index_auto
