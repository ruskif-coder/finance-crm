-- Индексы и ограничения, живущие на боевой базе, но отсутствующие в репозитории.
--
-- Обнаружено 2026-08-23 тем же экспериментом: чистая база после полного старта
-- приложения И наката всех миграций получает 185 индексов из 210. Двадцать пять
-- заводились разово — часть скриптом add_db_indexes.sql времён укрепления
-- безопасности 2026-07-02 (упомянут в CLAUDE.md, самого файла в репозитории нет),
-- часть руками при работе над дашбордом продаж.
--
-- Пропажа индекса не роняет приложение — она делает его медленным, поэтому
-- заметить это на новой базе было бы нечем. Отсюда и решение записать их сюда.
--
-- Снято с боевой базы 2026-08-23, идемпотентно.

-- ── ограничения уникальности ────────────────────────────────────────────────
-- ADD CONSTRAINT IF NOT EXISTS в Postgres нет, поэтому проверяем pg_constraint.
-- Это не косметика: без ограничения на (role_id, section) роль может получить
-- две строки прав на один раздел, и какая из них подействует — вопрос везения.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'role_permissions_role_id_section_key') THEN
        ALTER TABLE role_permissions ADD CONSTRAINT role_permissions_role_id_section_key UNIQUE (role_id, section);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'login_attempts_email_key') THEN
        ALTER TABLE login_attempts ADD CONSTRAINT login_attempts_email_key UNIQUE (email);
    END IF;
END $$;

-- ── операции: основные фильтры реестра и отчётов ────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ops_date ON operations (date);
CREATE INDEX IF NOT EXISTS idx_ops_bank ON operations (bank);
CREATE INDEX IF NOT EXISTS idx_ops_article ON operations (article_id);
CREATE INDEX IF NOT EXISTS idx_ops_counterparty ON operations (counterparty_id);
CREATE INDEX IF NOT EXISTS idx_operations_own_company_id ON operations (own_company_id);

-- ── контрагенты и договоры ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_contracts_inn ON contracts (inn);
CREATE INDEX IF NOT EXISTS idx_contracts_counterparty ON contracts (counterparty_id);
-- Дубль предыдущего по тому же столбцу, приехал из другого прогона. Оставлен
-- ради совпадения с боевой; лишний индекс замедляет запись — кандидат на снос
-- отдельным решением.
CREATE INDEX IF NOT EXISTS ix_contracts_counterparty_id ON contracts (counterparty_id);
CREATE INDEX IF NOT EXISTS idx_cp_bank_accounts_cp_id ON counterparty_bank_accounts (counterparty_id);
-- Частичный: своих юрлиц единицы, полный индекс по булеву полю бесполезен.
CREATE INDEX IF NOT EXISTS idx_counterparties_is_own_company
    ON counterparties (is_own_company) WHERE (is_own_company = true);

-- ── журнал действий ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id, created_at DESC);

-- ── продажи ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sales_deals_modify ON sales_deals (date_modify);
CREATE INDEX IF NOT EXISTS idx_sales_deals_payer ON sales_deals (payer_name);
CREATE INDEX IF NOT EXISTS idx_sales_deals_annex ON sales_deals (annex_id);
CREATE INDEX IF NOT EXISTS idx_sales_brands_advertiser ON sales_brands (advertiser_id);
CREATE INDEX IF NOT EXISTS idx_sales_agencies_holding ON sales_agencies (holding);
CREATE INDEX IF NOT EXISTS idx_sales_agency_cp_agency ON sales_agency_counterparties (agency_id);
CREATE INDEX IF NOT EXISTS idx_sales_pstages_pipeline ON sales_pipeline_stages (pipeline_id);
CREATE INDEX IF NOT EXISTS idx_sales_price_service ON sales_price_list (service_id);
CREATE INDEX IF NOT EXISTS idx_sales_annex_items_annex ON sales_annex_items (annex_id);
CREATE INDEX IF NOT EXISTS idx_sales_annex_items_period ON sales_annex_items (period_from, period_to);
CREATE INDEX IF NOT EXISTS idx_sales_deleted_bid ON sales_deleted_deals (bitrix_id);
CREATE INDEX IF NOT EXISTS idx_sales_raw_lookup ON sales_bitrix_raw (entity, bitrix_id, fetched_at);
-- Частичные: очередь разбора и неотправленные правки — это всегда «открытые»
-- строки, полный индекс по всей таблице тут был бы напрасным.
CREATE INDEX IF NOT EXISTS idx_sales_match_open ON sales_match_queue (entity, resolved_at);
CREATE INDEX IF NOT EXISTS idx_sales_override_deal ON sales_deal_field_overrides (deal_id);
CREATE INDEX IF NOT EXISTS idx_sales_override_unpushed
    ON sales_deal_field_overrides (pushed_at) WHERE (pushed_at IS NULL);
