-- Справочник паблишеров (площадок).
--
-- Первичный источник — рабочая таблица «Аптеки»: 47 строк, из которых шесть сайтов
-- заведены дважды, отдельной строкой на WEB и на APP. Это и есть причина, по которой
-- площадка и поверхность разнесены на две таблицы: у сайта одно юрлицо, один договор,
-- один чат и одни контакты, а фигма, статус интеграции и покрытие мест — свои у веба
-- и своя у приложения. Одной строкой это выражается только дублированием всего
-- остального, что уже и произошло в Excel.
--
-- Юрлицо и договор — ссылками в реестры финмодуля, а не текстом: у ООО «ДПД Медиа»
-- один договор №25/08/23 на двадцать площадок, и при текстовом хранении смена этого
-- договора означала бы двадцать правок вручную.

-- ---------------------------------------------------------------- вид паблишера
-- Не отдельный раздел меню, а накопитель значений: введённое в карточке имя вида
-- сохраняется и дальше предлагается в выпадашке. Тот же приём, что у чипов
-- таргетинга (sales_targeting_items) — каталог заводить не на что.
CREATE TABLE IF NOT EXISTS sales_publisher_kinds (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR NOT NULL UNIQUE,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

INSERT INTO sales_publisher_kinds (name, sort_order)
VALUES ('Аптеки', 0)
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------- площадка
CREATE TABLE IF NOT EXISTS sales_publishers (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR NOT NULL,
    -- Ключ площадки. Хранится приведённым к нижнему регистру и без пробелов по краям:
    -- в исходной таблице один и тот же сайт встречается как «ETABL.RU », «ASNA.ru» и
    -- «Farmlend.ru», и без нормализации дубли не ловятся сравнением.
    domain        VARCHAR NOT NULL UNIQUE,
    -- Вид паблишера (значение из sales_publisher_kinds по имени, не FK: список
    -- пополняется вводом, а переименование вида не должно осиротить площадку).
    kind          VARCHAR,
    -- ПЕРЕГОВОРЫ | СОТРУДНИЧАЕМ | НА ПАУЗЕ | ОТКАЗ | АРХИВ
    status        VARCHAR NOT NULL DEFAULT 'ПЕРЕГОВОРЫ',
    -- Сеть аптек. NULL — независимая площадка: в Excel это писали словом
    -- «НЕЗАВИСИМЫЕ», из-за чего получалась несуществующая сеть на двадцать сайтов.
    network       VARCHAR,
    -- прямой | посредник
    deal_type     VARCHAR,
    -- Юрлицо посредника, через которое идёт договор (в исходных данных — ДПД Медиа).
    -- Заполняется только при deal_type = 'посредник'.
    intermediary_counterparty_id INTEGER REFERENCES counterparties(id),
    is_exclusive  BOOLEAN NOT NULL DEFAULT FALSE,
    has_dsp       BOOLEAN NOT NULL DEFAULT FALSE,
    is_priority   BOOLEAN NOT NULL DEFAULT FALSE,
    -- ДА | НЕТ | ЗАПРОСИТЬ — площадка размещает собственную рекламу
    self_promo    VARCHAR,
    self_promo_note TEXT,
    -- Закупочный CPM до НДС по договору с площадкой.
    cpm_contract  DOUBLE PRECISION,
    -- Наличие и устройство корзины/избранного на стороне площадки: от этого зависит,
    -- какие механики (например, коммуникация по отложенному товару) вообще возможны.
    basket_note   TEXT,
    note          TEXT,
    -- Рабочий чат. Ссылка есть не всегда — часть чатов известна только по названию.
    chat_title    VARCHAR,
    chat_url      VARCHAR,
    -- План перехода на другой мессенджер (у части площадок запрещён телеграм).
    messenger_note TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_publishers_status  ON sales_publishers (status);
CREATE INDEX IF NOT EXISTS ix_publishers_network ON sales_publishers (network);
CREATE INDEX IF NOT EXISTS ix_publishers_kind    ON sales_publishers (kind);

-- ---------------------------------------------------------------- поверхности
-- web | app. Отсутствие строки означает «поверхности нет и разговора не было» —
-- то же, что писали в Excel словами «ОТСТУТСТВУЕТ» и «не обсуждали».
CREATE TABLE IF NOT EXISTS sales_publisher_surfaces (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    kind         VARCHAR NOT NULL,
    figma_url    VARCHAR,
    -- НЕТ | ОТЛОЖЕНО | ПОДГОТОВКА | СОГЛАСОВАНИЕ | ПРАВКИ | ПОДКЛЮЧЕНО
    integration_status VARCHAR NOT NULL DEFAULT 'НЕТ',
    -- Доля занятых нами мест из доступных, %.
    coverage_percent   DOUBLE PRECISION,
    note         TEXT,
    CONSTRAINT uq_publisher_surface UNIQUE (publisher_id, kind)
);

-- ---------------------------------------------------------------- услуги
-- Галочка ставится на паре «услуга + поверхность»: у услуг с раздельным прайсом web и
-- app — разные тарифы (sales_services.separate_price), и подключены они бывают
-- по-разному. Хранить связь на уровне площадки значило бы терять эту разницу.
CREATE TABLE IF NOT EXISTS sales_publisher_services (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    surface_kind VARCHAR NOT NULL,
    service_id   INTEGER NOT NULL REFERENCES sales_services(id),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    note         TEXT,
    CONSTRAINT uq_publisher_service UNIQUE (publisher_id, surface_kind, service_id)
);

CREATE INDEX IF NOT EXISTS ix_publisher_services_service ON sales_publisher_services (service_id);

-- ---------------------------------------------------------------- юрлица
-- М:М: у площадки может быть несколько юрлиц, и одно юрлицо (ДПД Медиа) стоит
-- за многими площадками. Устроено так же, как sales_agency_counterparties.
CREATE TABLE IF NOT EXISTS sales_publisher_counterparties (
    id              SERIAL PRIMARY KEY,
    publisher_id    INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
    CONSTRAINT uq_publisher_counterparty UNIQUE (publisher_id, counterparty_id)
);

-- ---------------------------------------------------------------- договоры
-- role: 'с площадкой' — прямой договор на размещение; 'агентский' — агентский
-- договор с тем же паблишером. В исходной таблице это две отдельные колонки, у
-- одиннадцати площадок заполнены обе.
CREATE TABLE IF NOT EXISTS sales_publisher_contracts (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    contract_id  INTEGER NOT NULL REFERENCES contracts(id),
    role         VARCHAR NOT NULL DEFAULT 'с площадкой',
    CONSTRAINT uq_publisher_contract UNIQUE (publisher_id, contract_id, role)
);

-- ---------------------------------------------------------------- контакты
-- В Excel контакты размазаны по пяти колонкам, и в ячейке лежит по два-три человека
-- через «;» и перенос строки — то есть люди там уже есть, просто не разделены.
CREATE TABLE IF NOT EXISTS sales_publisher_contacts (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    name         VARCHAR,
    email        VARCHAR,
    telegram     VARCHAR,
    phone        VARCHAR,
    role         VARCHAR,
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    note         TEXT
);

CREATE INDEX IF NOT EXISTS ix_publisher_contacts_pub ON sales_publisher_contacts (publisher_id);
