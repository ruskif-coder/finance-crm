-- add_db_indexes.sql
-- Dobavlyaet nedostayushchiye indeksy dlya operations, contracts, audit_log.
-- CONCURRENTLY — ne blokiruyet tablitsu vo vremya sozdaniya (mozhno zapuskat' v zhivoy BD).
-- IF NOT EXISTS — idempotentno, bezopasno zapuskat' povtorno.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ops_date
    ON operations(date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ops_counterparty
    ON operations(counterparty_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ops_article
    ON operations(article_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ops_bank
    ON operations(bank);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contracts_inn
    ON contracts(inn);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contracts_counterparty
    ON contracts(counterparty_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_log_user
    ON audit_log(user_id, created_at DESC);

-- Proverka: spisok sozdannykh indeksov
SELECT
    indexname,
    tablename,
    indexdef
FROM pg_indexes
WHERE tablename IN ('operations', 'contracts', 'audit_log')
  AND schemaname = 'public'
ORDER BY tablename, indexname;
