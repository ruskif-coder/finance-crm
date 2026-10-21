-- Приоритезация (владелец 19.10.2026): сборка запроса аккаунтом, карточка площадке, заведение РК в системе приоритезации
-- (pp.simbad.pro) кнопкой «Запустить», суточная статистика с дельтой между снимками. Трафик не участвует.
-- Шаблон запроса: «шаблон запроса_ приоритезация.xlsx»; API: «API приоритизация.docx». Повторно накатываемая.

-- 1. Запрос по сделке — общая часть для всех площадок: собирает аккаунт.
CREATE TABLE IF NOT EXISTS prio_requests (
    id                  SERIAL PRIMARY KEY,
    deal_id             INTEGER NOT NULL UNIQUE REFERENCES sales_deals(id) ON DELETE CASCADE,
    product_name        VARCHAR(300),          -- название товара: бренд из сделки, правится
    target_competitors  TEXT,                  -- конкурирующие товары, через «, »
    target_mnn          TEXT,                  -- действующие вещества, через «, »
    target_meta         TEXT,                  -- ключевые слова / симптомы, через «, »
    date_start          DATE,                  -- период РК, из сделки
    date_end            DATE,
    erid_meta           VARCHAR(300),          -- данные рекламодателя или «самореклама»
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    updated_at          TIMESTAMP NOT NULL DEFAULT now(),
    updated_by          INTEGER REFERENCES users(id)
);

-- 2. Площадка запроса — пара «сделка × площадка» = одна РК в системе приоритезации.
CREATE TABLE IF NOT EXISTS prio_placements (
    id            SERIAL PRIMARY KEY,
    request_id    INTEGER NOT NULL REFERENCES prio_requests(id) ON DELETE CASCADE,
    publisher_id  INTEGER NOT NULL REFERENCES sales_publishers(id),
    product_id    VARCHAR(64),                 -- SKU у площадки — вписывает площадка
    product_url   VARCHAR(1000),               -- посадочная: страница препарата у площадки — вписывает АККАУНТ (живой процесс, 19.10)
    goal_imp      BIGINT CHECK (goal_imp >= 0),-- целевые показы: объём строки МП по площадке
    erid          VARCHAR(64),                 -- ЕРИД пары
    -- черновик → у площадки → правки → согласовано → идёт ⇄ остановлено; отказ — конечный
    status        VARCHAR(20) NOT NULL DEFAULT 'черновик',
    camp_id       INTEGER,                     -- id РК в системе приоритезации (нужен для правок, старта/стопа)
    tracker       JSONB,                       -- ссылки трекера из ответа заведения (imp/clk по search/catalog/context)
    toggle_on     BOOLEAN,                     -- последнее отправленное состояние «включена»
    comment       TEXT,                        -- последнее замечание (площадка ↔ аккаунт)
    comment_by    INTEGER REFERENCES users(id),
    comment_at    TIMESTAMP,
    sent_at       TIMESTAMP,                   -- отправлено площадке
    approved_at   TIMESTAMP,                   -- площадка согласовала
    launched_at   TIMESTAMP,                   -- заведено и запущено
    updated_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_prio_placement UNIQUE (request_id, publisher_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_prio_camp ON prio_placements (camp_id) WHERE camp_id IS NOT NULL;

-- 3. id площадки в системе приоритезации (`site_id` в API).
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS prio_site_id INTEGER;

-- 4. Снимки суточной статистики: каждый запрос дня хранится; дельта — разница с предыдущим снимком того же дня
-- (день перезабирается несколько ночей и может дорасти). В факт РК идёт последний снимок.
CREATE TABLE IF NOT EXISTS prio_stat_raw (
    id            SERIAL PRIMARY KEY,
    camp_id       INTEGER NOT NULL,
    day           DATE NOT NULL,               -- сутки по МСК
    shows         BIGINT NOT NULL DEFAULT 0,
    clicks        BIGINT NOT NULL DEFAULT 0,
    by_type       JSONB,                       -- разбивка search / catalog / context, если отдаётся
    delta_shows   BIGINT,                      -- к предыдущему снимку этого дня; первый снимок — NULL
    delta_clicks  BIGINT,
    pulled_at     TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prio_stat_raw ON prio_stat_raw (camp_id, day, pulled_at);

-- Добавки 19.10 (владелец: «делай»): когда напомнили площадке; статус «отказ» — площадка отказала, причина обязательна,
-- РК в архив. Статусы: черновик → у площадки → правки → согласовано → идёт ⇄ остановлено; отказ — конечный.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS reminded_at TIMESTAMP;
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP;

-- Автостоп по выполнению плана (владелец 19.10.2026, вариант 2): когда система сама остановила площадку, достигшую цели.
-- Стоит один раз — ручной «Старт» после него означает докрутку, повторно не стопим.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS goal_reached_at timestamp;
