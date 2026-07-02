-- add_counterparty_requisites.sql
-- Расширение таблицы counterparties реквизитными полями +
-- новая таблица counterparty_bank_accounts для банковских счетов.
--
-- Запуск:
--   docker exec -i finance_db psql -U finance_user -d finance < add_counterparty_requisites.sql
--
-- Идемпотентно: все изменения через IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.

ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS kpp          varchar(50);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS ogrn         varchar(50);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS okpo         varchar(50);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS address      text;
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS phone        varchar(100);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS email        varchar(200);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS edo_id       varchar(200);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS director_name varchar(200);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS website      varchar(500);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS address_fact text;

CREATE TABLE IF NOT EXISTS counterparty_bank_accounts (
    id               serial  PRIMARY KEY,
    counterparty_id  integer NOT NULL REFERENCES counterparties(id) ON DELETE CASCADE,
    bank_name        varchar(200),
    rs               varchar(50),
    ks               varchar(50),
    bik              varchar(50),
    sort_order       integer DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cp_bank_accounts_cp_id
    ON counterparty_bank_accounts (counterparty_id);
