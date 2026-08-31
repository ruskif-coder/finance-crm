-- Схемные ALTER/CREATE INDEX выносятся со СТАРТА бэкенда в миграцию.
--
-- НАЙДЕНО 31.08.2026 при подъёме прода локально. Блок `with engine.begin()` в
-- app/main.py выполнял ~50 `ALTER TABLE … ADD COLUMN IF NOT EXISTS` и `CREATE INDEX`
-- при КАЖДОМ старте контейнера. На свежей базе (первый старт) эти ALTER'ы реально
-- заводят колонки — под AccessExclusiveLock, — а параллельные логины берут RowShareLock
-- на те же таблицы. Postgres ловит deadlock, зависшие bcrypt-воркеры исчерпывают пул, и
-- вход виснет насовсем. На проде это окно открыто ровно при первом старте нового кода.
--
-- Лечение — не «сделать DDL аккуратнее», а убрать его из процесса, который обслуживает
-- запросы. Схема правится ЗДЕСЬ, до старта кода (порядок «миграции до кода», навык
-- deploying-to-prod), один раз, без конкуренции. На старте остаётся только
-- `create_all` — он не берёт эксклюзивных блокировок на существующие таблицы (CREATE
-- TABLE IF NOT EXISTS для уже существующей — проверка каталога, не ALTER), и на свежей
-- базе создаёт таблицы сразу полными, так что эта миграция там становится no-op.
--
-- Всё идемпотентно (IF NOT EXISTS): на существующей базе, где колонки уже есть, накат —
-- пустая операция. Ни одного DROP/UPDATE/INSERT: перенос один-в-один того, что делал
-- стартовый блок; разрушающая часть давно живёт в 2026-08-23_startup_ddl_to_migrations.sql.

ALTER TABLE role_permissions  ADD COLUMN IF NOT EXISTS deals_scope VARCHAR DEFAULT 'all';
ALTER TABLE sales_agencies    ADD COLUMN IF NOT EXISTS bx_id VARCHAR;
ALTER TABLE sales_advertisers ADD COLUMN IF NOT EXISTS bx_id VARCHAR;
ALTER TABLE users             ADD COLUMN IF NOT EXISTS bitrix_user_id VARCHAR;
ALTER TABLE sales_agencies    ADD COLUMN IF NOT EXISTS bx_master VARCHAR;
ALTER TABLE sales_advertisers ADD COLUMN IF NOT EXISTS bx_master VARCHAR;
ALTER TABLE sales_reps        ADD COLUMN IF NOT EXISTS is_sales_head BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sales_agencies    ADD COLUMN IF NOT EXISTS sk_percent DOUBLE PRECISION NOT NULL DEFAULT 30;

ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS amount_with_vat DOUBLE PRECISION;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS brief TEXT;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS brief_synced_at TIMESTAMP;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS sync_status VARCHAR;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS sync_checked_at TIMESTAMP;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS sync_report JSONB;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS probability_color VARCHAR;      -- светофор вероятности
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS our_stage_id INTEGER;           -- движение по каталогу
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS code VARCHAR(6);                -- метка сделки
CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_deals_code ON sales_deals (code);
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS year_plan_line_id INTEGER;      -- линк на ячейку годового плана
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS plan_month INTEGER;
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS plan_deal_idx INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_sales_deals_year_plan_line ON sales_deals (year_plan_line_id);
CREATE INDEX IF NOT EXISTS ix_sales_deals_plan_link ON sales_deals (year_plan_line_id, plan_month, plan_deal_idx);
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS realization_pipeline_id INTEGER;

ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS plan_id INTEGER;
ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS brief JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS service_forecast JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS ix_sales_year_plan_lines_plan ON sales_year_plan_lines (plan_id);

ALTER TABLE sales_stage_phases ADD COLUMN IF NOT EXISTS is_realization BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sales_stages       ADD COLUMN IF NOT EXISTS requires_media_plan BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sales_stages       ADD COLUMN IF NOT EXISTS stage_key VARCHAR;       -- под-этап 2/2/2

-- Справочник услуг: параметры конструктора МП (циклы стартового блока развёрнуты).
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS placement_type VARCHAR;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS calc_form VARCHAR;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS unit_price DOUBLE PRECISION;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS unit_price_web DOUBLE PRECISION;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS unit_price_app DOUBLE PRECISION;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS separate_price BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS constants JSONB;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS bx_id VARCHAR;               -- связь с СП 1050 Битрикса
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS bx_title VARCHAR;
ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS revenue_article_id INTEGER;  -- услуга → статья выручки
CREATE INDEX IF NOT EXISTS ix_sales_services_bx_id ON sales_services (bx_id);

ALTER TABLE sales_addon_services ADD COLUMN IF NOT EXISTS period VARCHAR;

ALTER TABLE roles ADD COLUMN IF NOT EXISTS staff_group VARCHAR;                  -- рабочая группа
ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_master BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE sales_media_plan_rows ADD COLUMN IF NOT EXISTS inventory VARCHAR;

-- Заморожены 30.08.2026 со стейт-машиной МП: колонки живы, их больше не пишут.
ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS reject_reason TEXT;
ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS decided_by INTEGER;
ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;

-- Право согласования (креативы и очередь трафика — см. permissions.py).
ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS can_approve INTEGER DEFAULT 0;

-- Индексы витрины продаж и уведомлений.
CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications (user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sales_deals_stage      ON sales_deals (pipeline, bitrix_stage);
CREATE INDEX IF NOT EXISTS idx_sales_deals_rep        ON sales_deals (sales_rep_id);
CREATE INDEX IF NOT EXISTS idx_sales_deals_acct       ON sales_deals (account_manager_id);
CREATE INDEX IF NOT EXISTS idx_sales_deals_advertiser ON sales_deals (advertiser_id);
CREATE INDEX IF NOT EXISTS idx_sales_deals_agency     ON sales_deals (agency_id);
CREATE INDEX IF NOT EXISTS idx_sales_deals_period     ON sales_deals (period_from, period_to);

-- ── Внешние ключи (тоже со старта) ──────────────────────────────────────────
-- Раньше их заводил `add_missing_foreign_keys()` при каждом старте: ADD CONSTRAINT
-- FOREIGN KEY берёт ShareRowExclusiveLock и валидирует данные — тот же класс блокировок,
-- что деадлочил вход. Стартовый код был терпим к висячим ссылкам (лог и продолжение,
-- чтобы контейнер поднялся); здесь та же терпимость — DO-блок ловит foreign_key_violation
-- и пишет NOTICE вместо аборта, а существующий ключ пропускает. Идемпотентно.
DO $$
DECLARE
    fk RECORD;
BEGIN
    FOR fk IN
        SELECT * FROM (VALUES
            ('sales_deals_our_stage_id_fkey',        'sales_deals',           'our_stage_id',      'sales_stages(id)'),
            ('sales_deals_year_plan_line_id_fkey',   'sales_deals',           'year_plan_line_id', 'sales_year_plan_lines(id)'),
            ('sales_year_plan_lines_plan_id_fkey',   'sales_year_plan_lines', 'plan_id',           'sales_year_plans(id)')
        ) AS t(name, tbl, col, ref)
    LOOP
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = fk.name) THEN
            CONTINUE;
        END IF;
        BEGIN
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %s',
                           fk.tbl, fk.name, fk.col, fk.ref);
            RAISE NOTICE 'FK % создан', fk.name;
        EXCEPTION WHEN foreign_key_violation THEN
            RAISE NOTICE 'FK % не создан: есть висячие ссылки — расчистите и накатите повторно', fk.name;
        END;
    END LOOP;
END $$;
