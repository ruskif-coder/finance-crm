-- Зеркало справочников ОРД (МедиаСкаут), этап 1.
-- Схема согласована с владельцем 25.08.2026, см. docs/SCHEMA_обвязка_ОРД_на_согласование.md
--
-- Зеркало асимметрично по природе строки: где мастер ОРД (клиенты, договоры) — это кэш
-- чтения; где мастер мы (креативы) — журнал передачи. Поля status/status_at/error_text
-- есть везде, потому что регистрация в ЕРИР асинхронная: ответ 201 не означает, что
-- запись принята.
--
-- Роль юрлица (заказчик / рекламодатель / исполнитель / площадка) НЕ хранится: из 171
-- юрлица в ОРД 28 играют больше одной роли: одно и то же лицо бывает и заказчиком,
-- и рекламодателем. Роль читается из того, каким полем какого договора юрлицо является.

CREATE TABLE IF NOT EXISTS ord_clients (
    id              SERIAL PRIMARY KEY,
    ord_id          VARCHAR(64)  NOT NULL UNIQUE,   -- строка вида «CTxxxxxxxxxxxxxxxxxxxxxx»
    ord_cid         VARCHAR(64),                    -- второй идентификатор ОРД
    inn             VARCHAR(20),                    -- ключ сопоставления; у иностранцев пусто
    reg_number      VARCHAR(64),                    -- вместо ИНН для иностранных лиц
    oksm            VARCHAR(8),                     -- код страны регистрации
    name            TEXT         NOT NULL,
    legal_form      VARCHAR(40),                    -- JuridicalPerson и т.д.
    mobile_phone    VARCHAR(40),
    epay_number     VARCHAR(64),
    counterparty_id INTEGER REFERENCES counterparties(id),
    status          VARCHAR(40),
    status_at       TIMESTAMP,
    error_text      TEXT,
    origin          VARCHAR(8) NOT NULL DEFAULT 'ord',  -- 'ord' прочитан | 'ours' заведён нами
    synced_at       TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ord_clients_inn ON ord_clients(inn);

CREATE TABLE IF NOT EXISTS ord_final_contracts (
    id              SERIAL PRIMARY KEY,
    ord_id          VARCHAR(64)  NOT NULL UNIQUE,
    ord_cid         VARCHAR(64),
    number          VARCHAR(128),     -- у 6 из 152 договоров номера нет вовсе
    date            DATE         NOT NULL,
    expiration_date DATE,             -- заполнен у 2 из 152
    amount          NUMERIC(18,2),    -- заполнен у 1 из 152, и там ноль
    type            VARCHAR(40),
    subject_type    VARCHAR(40),
    action_type     VARCHAR(40),
    is_agent_acting_for_publisher BOOLEAN,
    client_id       INTEGER NOT NULL REFERENCES ord_clients(id),   -- заказчик
    partner_id      INTEGER REFERENCES ord_clients(id),
    parent_number   VARCHAR(128),     -- номер основного договора для доп. соглашений
    status          VARCHAR(40),
    status_at       TIMESTAMP,
    error_text      TEXT,
    origin          VARCHAR(8) NOT NULL DEFAULT 'ord',
    synced_at       TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ord_final_client ON ord_final_contracts(client_id);

CREATE TABLE IF NOT EXISTS ord_initial_contracts (
    id                SERIAL PRIMARY KEY,
    ord_id            VARCHAR(64)  NOT NULL UNIQUE,
    ord_cid           VARCHAR(64),
    number            VARCHAR(128),
    date              DATE         NOT NULL,
    expiration_date   DATE,
    amount            NUMERIC(18,2),
    type              VARCHAR(40),
    subject_type      VARCHAR(40),
    action_type       VARCHAR(40),
    is_agent_acting_for_publisher BOOLEAN,
    client_id         INTEGER NOT NULL REFERENCES ord_clients(id),          -- РЕКЛАМОДАТЕЛЬ
    contractor_id     INTEGER NOT NULL REFERENCES ord_clients(id),          -- ИСПОЛНИТЕЛЬ
    final_contract_id INTEGER NOT NULL REFERENCES ord_final_contracts(id),
    status            VARCHAR(40),
    status_at         TIMESTAMP,
    error_text        TEXT,
    origin            VARCHAR(8) NOT NULL DEFAULT 'ord',
    synced_at         TIMESTAMP
);
-- Ключ подбора на экране сборки: под доходным ищем договоры нужного рекламодателя.
CREATE INDEX IF NOT EXISTS ix_ord_initial_pick
    ON ord_initial_contracts(final_contract_id, client_id);

CREATE TABLE IF NOT EXISTS ord_outer_contracts (
    id              SERIAL PRIMARY KEY,
    ord_id          VARCHAR(64)  NOT NULL UNIQUE,
    ord_cid         VARCHAR(64),
    number          VARCHAR(128),
    date            DATE         NOT NULL,
    expiration_date DATE,
    amount          NUMERIC(18,2),
    type            VARCHAR(40),
    subject_type    VARCHAR(40),
    action_type     VARCHAR(40),
    is_agent_acting_for_publisher BOOLEAN,
    is_reg_report   BOOLEAN,
    contractor_id   INTEGER NOT NULL REFERENCES ord_clients(id),   -- площадка
    partner_id      INTEGER REFERENCES ord_clients(id),
    status          VARCHAR(40),
    status_at       TIMESTAMP,
    error_text      TEXT,
    origin          VARCHAR(8) NOT NULL DEFAULT 'ord',
    synced_at       TIMESTAMP
);

-- Мастер — мы. Строка не справочник, а запись об отправке.
CREATE TABLE IF NOT EXISTS ord_creatives (
    id                  SERIAL PRIMARY KEY,
    -- Ключ идемпотентности: без него повтор запроса после сбоя сети заводит дубль в ЕРИР.
    native_customer_id  VARCHAR(64)  NOT NULL UNIQUE,
    ord_id              VARCHAR(64)  UNIQUE,
    erid                VARCHAR(64),          -- приходит сразу, ещё до регистрации
    status              VARCHAR(40),          -- Creating..Active | RegistrationError
    status_at           TIMESTAMP,
    error_text          TEXT,                 -- erirValidationError
    final_contract_id   INTEGER REFERENCES ord_final_contracts(id),
    initial_contract_id INTEGER REFERENCES ord_initial_contracts(id),
    creative_set_id     INTEGER,              -- → launch_prep_creative_set, когда появится
    created_at          TIMESTAMP DEFAULT now(),
    synced_at           TIMESTAMP
);

-- Привязка сборки. Доходный договор НЕ хранится: он выводится как
-- ord_initial_contracts.final_contract_id. Хранить оба значит держать возможность
-- рассинхрона между ними.
ALTER TABLE sales_deals
    ADD COLUMN IF NOT EXISTS ord_initial_contract_id INTEGER
    REFERENCES ord_initial_contracts(id);
