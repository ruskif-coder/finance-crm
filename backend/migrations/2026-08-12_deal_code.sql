-- Метка сделки (наш 6-значный отпечаток). bitrix_id НЕ трогаем (несущий ключ синка).
-- Локально:
--   docker exec -i finance_db psql -U finance_user -d finance < backend/migrations/2026-08-12_deal_code.sql
-- Затем бэкфилл (генерит уникальные коды всем сделкам без кода):
--   docker exec finance_backend python -m app.sales.backfill_deal_codes

ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS code VARCHAR(6);
-- UNIQUE-индекс: NULL'ы допускаются (заполнятся бэкфиллом), дубли кода запрещены.
CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_deals_code ON sales_deals(code);
