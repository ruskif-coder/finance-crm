-- Дашборд трафика: рекламные кампании (РК), площадки, креативы в DSP, каталог блоков, факт.
-- Спека: docs/SPEC_дашборд_трафика.md. Согласовано владельцем 01.09.2026.
--
-- Грань: 1 РК = 1 сделка; распределение — на площадке; сам креатив в МС —
-- на связке площадка×креатив (у каждого свой ЕРИД и сквозное имя). Веса площадок НЕ
-- дублируем — берём из sales_publisher_traffics. Комплект/файлы/пары — из launch_prep_*.
--
-- Идемпотентно (IF NOT EXISTS). Только добавляющие операции. ЛОКАЛЬНО — в прод отдельно.

-- ── 1. РК: одна на сделку ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ad_campaign (
    id                 SERIAL PRIMARY KEY,
    deal_id            INTEGER NOT NULL UNIQUE REFERENCES sales_deals(id) ON DELETE CASCADE,
    -- активный комплект креативов; NULL пока сделка «ожидает сборки» и комплекта ещё нет
    set_id             INTEGER REFERENCES launch_prep_creative_set(id) ON DELETE SET NULL,
    month              DATE,                       -- 1-е число календарного месяца РК
    status             VARCHAR(32) NOT NULL DEFAULT 'ожидает сборки',
    date_start         DATE,
    date_end           DATE,
    plan_show          DOUBLE PRECISION,           -- = лимиты кампании в МС
    plan_click         DOUBLE PRECISION,
    plan_budget        DOUBLE PRECISION,
    ms_campaign_xxhash VARCHAR(64),                -- id кампании в DSP (после Campaign.add)
    ms_synced_at       TIMESTAMP,
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    updated_at         TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ad_campaign_status ON ad_campaign (status);
CREATE INDEX IF NOT EXISTS ix_ad_campaign_month  ON ad_campaign (month);

-- ── 2. Площадка внутри РК = source в МС (уровень распределения) ──────────────
CREATE TABLE IF NOT EXISTS ad_campaign_placement (
    id               SERIAL PRIMARY KEY,
    campaign_id      INTEGER NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    publisher_id     INTEGER NOT NULL REFERENCES sales_publishers(id),
    ms_source_key    VARCHAR(64),                  -- x-simb-web (web) / x-simb (app) + блок
    weight           DOUBLE PRECISION,             -- снимок веса из sales_publisher_traffics
    share            DOUBLE PRECISION,             -- доля % (пересчёт при выпадении площадок)
    plan_show        DOUBLE PRECISION,             -- план показов площадки
    daily_limit_plan DOUBLE PRECISION,             -- суточный ОРИЕНТИР (день-в-день рулит МС uniform_pro)
    bid              DOUBLE PRECISION,             -- ставка source (наш рычаг распределения)
    status           VARCHAR(32) NOT NULL DEFAULT 'вкл',   -- вкл | выкл | пауза
    is_direct        BOOLEAN NOT NULL DEFAULT FALSE,       -- «крутит сама» (10%) — факт руками
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, publisher_id)
);
CREATE INDEX IF NOT EXISTS ix_ad_placement_campaign ON ad_campaign_placement (campaign_id);

-- ── 3. Креатив в МС: связка площадка×креатив (сквозное имя, свой ЕРИД) ───────
CREATE TABLE IF NOT EXISTS ad_campaign_creative (
    id                 SERIAL PRIMARY KEY,
    campaign_id        INTEGER NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    placement_id       INTEGER NOT NULL REFERENCES ad_campaign_placement(id) ON DELETE CASCADE,
    file_id            INTEGER REFERENCES launch_prep_creative_file(id) ON DELETE SET NULL,  -- наш zip
    creative_no        INTEGER NOT NULL,           -- cr№ (порядковый)
    ms_creative_xxhash VARCHAR(64),                -- id креатива в МС (после Creative.add)
    erid               VARCHAR(64),                -- свой ЕРИД на связку
    ms_title           VARCHAR(255),               -- сквозное имя: <deal.code>-<publisher.code>-cr<no>
    status             VARCHAR(32) NOT NULL DEFAULT 'создан',
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    updated_at         TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (placement_id, creative_no)
);
CREATE INDEX IF NOT EXISTS ix_ad_creative_campaign ON ad_campaign_creative (campaign_id);

-- ── 4. Каталог рекламных блоков (импорт из «Площадки и блоки.xlsx») ──────────
CREATE TABLE IF NOT EXISTS publisher_block (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    surface      VARCHAR(8),                       -- web | app
    ms_block_id  VARCHAR(64),                      -- id блока в МС
    name         VARCHAR(255),                     -- название блока (cart / aboveReco)
    page_type    VARCHAR(64),                      -- главная/каталог/карточка/корзина/статьи/акции/лк
    network      VARCHAR(32),                      -- x-simb-web / x-simb
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_publisher_block_pub ON publisher_block (publisher_id);

-- ── 5. Факт показов/кликов (из stat-API МС; разрез по площадке — если API даёт) ─
CREATE TABLE IF NOT EXISTS ad_campaign_stat (
    id           SERIAL PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    placement_id INTEGER REFERENCES ad_campaign_placement(id) ON DELETE CASCADE,  -- NULL = без разреза
    date         DATE NOT NULL,
    shows        INTEGER NOT NULL DEFAULT 0,
    clicks       INTEGER NOT NULL DEFAULT 0,
    source       VARCHAR(16) NOT NULL DEFAULT 'ms',      -- ms | manual (для «прямых» 10%)
    imported_at  TIMESTAMP NOT NULL DEFAULT now(),
    -- идемпотентный ре-импорт: одна строка на (РК, площадка, сутки, источник).
    -- NULLS NOT DISTINCT (Postgres 15+): без него строки с placement_id=NULL (когда
    -- stat-API не даёт разрез по площадке) считались бы РАЗНЫМИ и дубли пролезли бы.
    CONSTRAINT uq_ad_stat UNIQUE NULLS NOT DISTINCT (campaign_id, placement_id, date, source)
);
CREATE INDEX IF NOT EXISTS ix_ad_stat_campaign_date ON ad_campaign_stat (campaign_id, date);

-- ── Правки существующих таблиц ──────────────────────────────────────────────
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS ms_publisher_id VARCHAR;   -- id площадки в МС
ALTER TABLE sales_services   ADD COLUMN IF NOT EXISTS dsp_wrapper_html TEXT;      -- HTML-обёртка + viewability-скрипт

-- ── Настройка сквозного наименования: по нашему коду (решение владельца) ─────
INSERT INTO company_settings (key, value)
SELECT 'dsp_name_publisher_ref', 'code'
WHERE NOT EXISTS (SELECT 1 FROM company_settings WHERE key = 'dsp_name_publisher_ref');
