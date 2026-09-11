-- Аналитическая база DSP (контур «DSP-коннектор», этап 2a). Накатывается в ОТДЕЛЬНУЮ базу
-- dsp_analytics (контейнер finance_dsp_db, TimescaleDB на pg16), НЕ в основную finance:
--     docker exec -i finance_dsp_db psql -U dsp -d dsp_analytics < backend/migrations/dsp/2026-09-02_dsp_analytics.sql
-- Состав согласован владельцем 01–02.09.2026 (docs/SPEC_дашборд_трафика.md §7.2).
-- Сырьё stat-API DSP в полном разрезе; в основную базу отдаётся ТОЛЬКО суточный срез
-- (upsert в ad_campaign_stat). ORM эти таблицы не описывает: hypertable/continuous aggregate —
-- DDL Timescale, create_all их не создаст. Идемпотентно.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ── 1. Сырьё статистики (hypertable по ts) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS dsp_stat_raw (
    ts                  TIMESTAMPTZ NOT NULL,          -- гранула stat-API (сутки или час)
    ms_campaign_xxhash  VARCHAR(16) NOT NULL,          -- ↔ ad_campaign.ms_campaign_xxhash
    ms_source_key       VARCHAR(64),                   -- source (площадка) — NULL, если API без разреза
    ms_creative_xxhash  VARCHAR(16),                   -- ↔ ad_campaign_creative.ms_creative_xxhash
    shows               INTEGER NOT NULL DEFAULT 0,
    clicks              INTEGER NOT NULL DEFAULT 0,
    spend               NUMERIC(14,4),                 -- расход, если stat-API отдаёт
    imported_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- идемпотентный ре-пул: одна строка на гранулу × РК × source × креатив.
    -- NULLS NOT DISTINCT — иначе строки без разреза (NULL) считались бы разными и дублировались.
    CONSTRAINT uq_dsp_stat_raw UNIQUE NULLS NOT DISTINCT (ts, ms_campaign_xxhash, ms_source_key, ms_creative_xxhash)
);
SELECT create_hypertable('dsp_stat_raw', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS ix_dsp_stat_raw_campaign_ts ON dsp_stat_raw (ms_campaign_xxhash, ts DESC);

-- компрессия старых чанков: сегментируем по РК+source (по ним и читаем), старше 30 дней
ALTER TABLE dsp_stat_raw SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ms_campaign_xxhash, ms_source_key',
    timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('dsp_stat_raw', INTERVAL '30 days', if_not_exists => TRUE);

-- ── 2. Суточный срез (continuous aggregate) — источник для апсерта в основную базу ──
CREATE MATERIALIZED VIEW IF NOT EXISTS dsp_stat_daily
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', ts) AS day,
       ms_campaign_xxhash,
       ms_source_key,
       sum(shows)  AS shows,
       sum(clicks) AS clicks,
       sum(spend)  AS spend
FROM dsp_stat_raw
GROUP BY 1, 2, 3
WITH NO DATA;
-- обновление: последние 3 дня пересчитываются каждый час (stat-API «дозаливает» вчера)
SELECT add_continuous_aggregate_policy('dsp_stat_daily',
    start_offset      => INTERVAL '3 days',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE);

-- ── 3. Журнал отправок в МС (против дублей + аудит, как журнал ОРД) ────────────
CREATE TABLE IF NOT EXISTS dsp_send_log (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    method       VARCHAR(64) NOT NULL,                 -- Campaign.add / Creative.add / Targeting.setUserSetting …
    entity_type  VARCHAR(32),                          -- campaign | creative | targeting | upload
    local_ref    VARCHAR(64),                          -- наш id (ad_campaign.id / ad_campaign_creative.id)
    request      JSONB,
    response     JSONB,
    ms_xxhash    VARCHAR(16),                          -- хеш из ответа (result) — что МС вернул
    ok           BOOLEAN NOT NULL DEFAULT FALSE,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS ix_dsp_send_log_ref ON dsp_send_log (entity_type, local_ref);
CREATE INDEX IF NOT EXISTS ix_dsp_send_log_xxhash ON dsp_send_log (ms_xxhash);

-- ── 4. Курсор выкачки: докуда забрали статистику по каждой РК ───────────────────
CREATE TABLE IF NOT EXISTS dsp_sync_cursor (
    ms_campaign_xxhash  VARCHAR(16) PRIMARY KEY,
    last_pulled_ts      TIMESTAMPTZ,                   -- последняя гранула, уже в dsp_stat_raw
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
