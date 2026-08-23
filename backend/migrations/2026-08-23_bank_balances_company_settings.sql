-- Две таблицы, которых не было в контроле версий НИКОГДА.
--
-- Обнаружено 2026-08-23 экспериментом: на пустой базе полный старт приложения
-- (create_all + стартовый блок main.py + сидеры) даёт 76 таблиц из 78. Не хватало
-- ровно этих двух — ORM-моделей у них нет, и ни одна миграция их не создавала.
-- Рецепт `bank_balances` существовал только внутри дампов в backups/: таблицу
-- когда-то завели руками в psql и не записали. `company_settings` создавалась
-- файлом из корневой scripts/, то есть из папки, целиком закрытой .gitignore.
--
-- Практическое следствие было такое: поднять рабочую систему из репозитория
-- нельзя — приложение падало бы на экране остатков, потому что settings.py и
-- reports.py читают bank_balances сырым SQL (ORM-модели, повторюсь, нет).
--
-- DDL снят с боевой базы 2026-08-23 и повторяет её один в один. На уже живых
-- стендах миграция ничего не меняет: всё под IF NOT EXISTS.

-- Остатки по банковским счетам + реквизиты плательщика для выгрузки платёжек.
-- bank — название банка из закрытого списка (АльфаБанк / ОПТ Банк / Совкомбанк /
-- Наличные), сравнивается в коде буквально, поэтому UNIQUE именно по нему.
CREATE TABLE IF NOT EXISTS bank_balances (
    id              SERIAL PRIMARY KEY,
    bank            VARCHAR NOT NULL UNIQUE,
    opening_balance DOUBLE PRECISION DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT now(),
    -- Реквизиты компании-плательщика: заполняются в Настройках → Остатки и
    -- подставляются в платёжные поручения.
    company_name    VARCHAR(255),
    inn             VARCHAR(12),
    kpp             VARCHAR(9),
    rs              VARCHAR(20),
    bik             VARCHAR(9),
    bank_full_name  VARCHAR(255),
    bank_city       VARCHAR(255),
    ks              VARCHAR(20),
    -- Какое из наших юрлиц владеет счётом. ON DELETE SET NULL: удаление
    -- контрагента не должно уносить с собой остаток по счёту.
    own_company_id  INTEGER REFERENCES counterparties(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_bank_balances_own_company_id
    ON bank_balances (own_company_id);

-- Настройки уровня компании «ключ → значение». Сейчас хранит счётчик номеров
-- платёжных поручений (payment_number_last).
CREATE TABLE IF NOT EXISTS company_settings (
    key   VARCHAR(255) PRIMARY KEY,
    value TEXT
);
