-- add_contract_documents.sql
-- Adds document_link and attached_filename columns to the contracts table.
-- Run via:
--   docker exec -i finance_db psql -U finance_user -d finance < add_contract_documents.sql
-- Idempotent: IF NOT EXISTS prevents errors on re-run.

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS document_link VARCHAR;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS attached_filename VARCHAR;
