-- Зеркало ОРД, вторая редакция. Заменяет форму из 2026-08-25_ord_mirror.sql.
-- Согласовано с владельцем 25.08.2026.
--
-- Что изменилось и почему:
--
-- 1. Изначальный договор привязан к НЕСКОЛЬКИМ доходным. Измерено по выгрузке:
--    152 строки листа = 126 договоров и 150 пар. Схема с одной колонкой
--    final_contract_id теряла 24 связи и 14 доходных из 41. Заведена таблица связи.
--
-- 2. Своя таблица нужна только изначальным договорам: это первое звено ЧУЖОЙ цепочки,
--    про которую мы знаем лишь часть. Юрлица и наши договоры переезжают в основные
--    справочники — пометкой на существующей строке, а не копией в зеркале.
--
-- 3. Стороны изначального хранятся атрибутами, а не ссылками: 87 из 91 рекламодателя
--    нам не контрагенты, счетов мы им не выставляем, и заводить их не нужно.
--
-- Таблицы ord_clients / ord_final_contracts / ord_outer_contracts из первой редакции
-- НЕ удаляются — замораживаются пустыми, по принятому в проекте правилу не сносить
-- то, что уже создано. Код их больше не читает.

-- ── пометки ОРД на основных справочниках ──────────────────────────────────────
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS ord_client_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_counterparties_ord_client ON counterparties(ord_client_id);

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS ord_contract_id VARCHAR(64);
-- final — доходный (заказчик платит нам), outer — расходный (платим мы площадке)
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS ord_kind       VARCHAR(8);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS ord_status     VARCHAR(40);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS ord_synced_at  TIMESTAMP;
CREATE UNIQUE INDEX IF NOT EXISTS ux_contracts_ord_contract
    ON contracts(ord_contract_id) WHERE ord_contract_id IS NOT NULL;

-- ── справочник изначальных договоров ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ord_initial_contracts (
    id              SERIAL PRIMARY KEY,
    ord_id          VARCHAR(64)  NOT NULL UNIQUE,
    ord_cid         VARCHAR(64),
    number          VARCHAR(128),          -- у части договоров номера нет вовсе
    date            DATE         NOT NULL,
    expiration_date DATE,
    amount          NUMERIC(18,2),
    type            VARCHAR(40),           -- мягкие: незнакомая подпись даёт NULL
    subject_type    VARCHAR(40),           -- и предупреждение импорта, а не отказ
    action_type     VARCHAR(40),
    is_agent_acting_for_publisher BOOLEAN,
    -- Стороны — атрибутами. Это первое звено чужой цепочки: мы знаем ИНН и название,
    -- но эти лица нам не контрагенты и заводить их в справочник не нужно.
    advertiser_inn  VARCHAR(20),
    advertiser_name TEXT,
    contractor_inn  VARCHAR(20),
    contractor_name TEXT,
    status          VARCHAR(40),
    status_at       TIMESTAMP,
    error_text      TEXT,
    origin          VARCHAR(8) NOT NULL DEFAULT 'ord',   -- ord | ours
    synced_at       TIMESTAMP
);

-- На локальном стенде эта таблица уже существовала после первой редакции (измерено:
-- 126 строк) со старой формой — NOT NULL FK client_id/contractor_id/final_contract_id
-- на ord_clients/ord_final_contracts. CREATE TABLE IF NOT EXISTS выше её не меняет,
-- когда она уже есть. Досоздаём недостающие колонки явно (ADD COLUMN IF NOT EXISTS
-- безопасен и на только что созданной этим же файлом таблице — там они уже есть).
ALTER TABLE ord_initial_contracts ADD COLUMN IF NOT EXISTS advertiser_inn  VARCHAR(20);
ALTER TABLE ord_initial_contracts ADD COLUMN IF NOT EXISTS advertiser_name TEXT;
ALTER TABLE ord_initial_contracts ADD COLUMN IF NOT EXISTS contractor_inn  VARCHAR(20);
ALTER TABLE ord_initial_contracts ADD COLUMN IF NOT EXISTS contractor_name TEXT;

-- Старые client_id/contractor_id/final_contract_id колонки не удаляются (замораживаются,
-- как и ord_clients/ord_final_contracts, на которые они ссылались) — снимается только
-- NOT NULL, иначе новый импортёр, который эти поля больше не заполняет, не сможет
-- вставить ни одной строки. На чистой базе, где таблицу только что создал блок выше в
-- новой форме, этих колонок нет вовсе — блок ничего не делает (проверяется явно, а не
-- через try/except, потому что ALTER COLUMN ... DROP NOT NULL не имеет формы IF EXISTS).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'ord_initial_contracts' AND column_name = 'client_id') THEN
        ALTER TABLE ord_initial_contracts ALTER COLUMN client_id DROP NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'ord_initial_contracts' AND column_name = 'contractor_id') THEN
        ALTER TABLE ord_initial_contracts ALTER COLUMN contractor_id DROP NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'ord_initial_contracts' AND column_name = 'final_contract_id') THEN
        ALTER TABLE ord_initial_contracts ALTER COLUMN final_contract_id DROP NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_ord_initial_advertiser
    ON ord_initial_contracts(advertiser_inn);

-- ── связь изначального с нашими доходными ─────────────────────────────────────
-- Ссылка идёт на ИДЕНТИФИКАТОР доходного в ОРД, а не на contracts.id: четыре
-- доходных договора из 52 у нас пока не заведены, и связь для них не должна
-- пропадать. contract_id заполняется, когда наш договор находится.
CREATE TABLE IF NOT EXISTS ord_initial_final_links (
    id                  SERIAL PRIMARY KEY,
    initial_contract_id INTEGER NOT NULL REFERENCES ord_initial_contracts(id) ON DELETE CASCADE,
    final_ord_id        VARCHAR(64) NOT NULL,
    contract_id         INTEGER REFERENCES contracts(id),
    synced_at           TIMESTAMP,
    UNIQUE (initial_contract_id, final_ord_id)
);
CREATE INDEX IF NOT EXISTS ix_ord_link_final ON ord_initial_final_links(final_ord_id);

-- ── журнал передачи креативов ─────────────────────────────────────────────────
-- Колонки final_contract_id / initial_contract_id первой редакции ссылались на
-- замороженные таблицы. Добавляются новые; старые остаются, кодом не читаются.
ALTER TABLE ord_creatives ADD COLUMN IF NOT EXISTS final_ord_id VARCHAR(64);
ALTER TABLE ord_creatives ADD COLUMN IF NOT EXISTS initial_id   INTEGER
    REFERENCES ord_initial_contracts(id);
