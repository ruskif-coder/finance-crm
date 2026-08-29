-- Модуль креативов: сбор запуска внутри ядра.
-- Состав согласован с владельцем 26.08.2026, см. docs/SCHEMA_креативы_на_согласование.md
-- Логика движения — артефакт «Движение креатива», план работ — docs/PLAN_модуль_креативов.md
--
-- Три сущности вместо одной, и путать их нельзя:
--   получатель  — пара «сделка × площадка», ДОЛГОживущая, несёт состояние;
--   комплект    — материал и его итерация, принадлежит СДЕЛКЕ, состояния не хранит;
--   пара        — «комплект × получатель», единица согласования и учёта в DSP.
-- Состояние комплекта и пары ВЫЧИСЛЯЕТСЯ из вердиктов: хранимое производное разъезжается
-- с операндами. Состояние получателя хранится — это решение человека, а не следствие данных.
--
-- Перечисления (состояния, виды проверок, происхождение) намеренно БЕЗ CHECK: их состав
-- будет меняться (модуль трафиков добавит свои под-этапы), а закреплены они тестами —
-- расширение не должно требовать миграции. Единственный CHECK здесь про смысл ссылки,
-- а не про словарь значений.

-- ── 1. Получатель задания ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS launch_prep_target (
    id             SERIAL PRIMARY KEY,
    deal_id        INTEGER NOT NULL REFERENCES sales_deals(id) ON DELETE CASCADE,
    -- Без каскада намеренно: площадка уходит в АРХИВ статусом, а не удалением.
    publisher_id   INTEGER NOT NULL REFERENCES sales_publishers(id),
    -- Снимок услуги на момент отправки. Она же ключ подстановки получателей.
    -- Ссылки на услугу у сделки нет, но услуга известна: sales_deals.product хранит имя
    -- из справочника и по живым сделкам совпадает в 297 случаях из 298 (замер 26.08.2026).
    service_id     INTEGER NOT NULL REFERENCES sales_services(id),
    surface_kind   VARCHAR(8) NOT NULL,           -- web | app
    -- согласование · согласован · ерид получен · заведён в DSP · в размещении ·
    -- завершён · сверка завершена · архив.
    -- «Заведён в DSP» — работа модуля трафиков, которого ещё нет: состояние заводится
    -- сразу, но проскакивается. Наружу три состояния после маркера сворачиваются в одно
    -- («ЕРИД получен») — свёртка ВЫЧИСЛЯЕТСЯ, второго поля под неё нет.
    state          VARCHAR(32) NOT NULL DEFAULT 'согласование',
    period_from    DATE,
    period_to      DATE,
    ord_submitted_at TIMESTAMP,                   -- сдан в ОРД: условие ухода в архив
    archived_at    TIMESTAMP,                     -- от неё считаются 180 дней до скрытия
    created_at     TIMESTAMP DEFAULT now(),
    updated_at     TIMESTAMP,
    CONSTRAINT uq_launch_prep_target UNIQUE (deal_id, publisher_id)
);
CREATE INDEX IF NOT EXISTS ix_lp_target_deal      ON launch_prep_target(deal_id);
CREATE INDEX IF NOT EXISTS ix_lp_target_publisher ON launch_prep_target(publisher_id);
CREATE INDEX IF NOT EXISTS ix_lp_target_state     ON launch_prep_target(state);

-- ── 2. Комплект креативов, он же итерация ───────────────────────────────────
CREATE TABLE IF NOT EXISTS launch_prep_creative_set (
    id             SERIAL PRIMARY KEY,
    deal_id        INTEGER NOT NULL REFERENCES sales_deals(id) ON DELETE CASCADE,
    -- NULL = общий комплект для всех получателей; заполнен = персональный комплект
    -- площадки («есть площадки со сложными ТТ, к ним должна быть возможность прикрепить
    -- свой креатив»). Получатель берёт персональный, если он есть, иначе общий.
    publisher_id   INTEGER REFERENCES sales_publishers(id),
    no             INTEGER NOT NULL,              -- порядковый номер комплекта в сделке
    -- Зачем комплект появился: первичный | доработка | параллельный.
    -- НЕ выводится задним числом: комплект принадлежит сделке, а вердикты — парам, и у
    -- комплекта, завёрнутого одной площадкой и принятого другой, правильного ответа нет.
    origin         VARCHAR(16) NOT NULL DEFAULT 'первичный',
    -- Какой комплект заменяет эта доработка. SET NULL, а не CASCADE: удаление заменённого
    -- не должно уносить преемника.
    replaces_set_id INTEGER REFERENCES launch_prep_creative_set(id) ON DELETE SET NULL,
    sent_at        TIMESTAMP,                     -- отправлен на вторичную проверку
    -- Banner | BannerHtml5 | Video …: выводится из файлов, переопределяется руками.
    form           VARCHAR(32),
    kktu_code      VARCHAR(16),                   -- переопределение кода бренда
    description    TEXT,                          -- переопределение описания объекта
    erid           VARCHAR(64),
    -- 'наш' | 'площадки'. У саморекламы маркер выпускает площадка: без этого признака код
    -- не отличит «ещё не выпустили» от «не будет никогда» и будет опрашивать вечно.
    erid_source    VARCHAR(16) NOT NULL DEFAULT 'наш',
    ord_creative_id VARCHAR(64),
    -- Creating..Active | RegistrationError | MediaDownloadError (вторая ветка отказа —
    -- «файл не скачался», лечится перезаливкой, а не переделкой материала).
    ord_status     VARCHAR(40),
    ord_error      TEXT,                          -- erirValidationError
    ord_env        VARCHAR(8),                    -- demo | prod, рядом с идентификатором
    ord_synced_at  TIMESTAMP,
    created_at     TIMESTAMP DEFAULT now(),
    updated_at     TIMESTAMP,
    -- NULLS NOT DISTINCT обязательно: по умолчанию Postgres считает NULL различными и
    -- обычный UNIQUE пропустил бы два ОБЩИХ комплекта с одним номером. PG 16 это умеет.
    CONSTRAINT uq_lp_set_no UNIQUE NULLS NOT DISTINCT (deal_id, publisher_id, no),
    -- Ссылка имеет смысл только у доработки. Без проверки поле со временем наберёт
    -- «а мы тут похожий брали за основу», и цепочка перестанет означать что-либо.
    CONSTRAINT ck_lp_set_replaces CHECK (replaces_set_id IS NULL OR origin = 'доработка')
);
CREATE INDEX IF NOT EXISTS ix_lp_set_deal ON launch_prep_creative_set(deal_id);

-- ── 3. Файлы комплекта ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS launch_prep_creative_file (
    id             SERIAL PRIMARY KEY,
    set_id         INTEGER NOT NULL REFERENCES launch_prep_creative_set(id) ON DELETE CASCADE,
    ratio          VARCHAR(24),                   -- 300x600, 240x400 …
    -- ОТНОСИТЕЛЬНЫЙ ключ от корня хранилища (соглашение от 23.08.2026), вида
    -- creatives/cre<set_id>_<имя>. Имя несёт вид сущности — иначе файлы разных подсистем
    -- затирают друг друга в общем каталоге, как уже было у площадок (pub7_/con7_/doc7_).
    path           VARCHAR(512) NOT NULL,
    original_name  VARCHAR(255),
    content_type   VARCHAR(128),
    size_bytes     INTEGER,
    -- Распаковываемый архив (HTML5-баннер). Едет в ОРД тем же признаком isArchive.
    is_archive     BOOLEAN NOT NULL DEFAULT false,
    uploaded_at    TIMESTAMP DEFAULT now(),
    uploaded_by    INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_lp_file_set ON launch_prep_creative_file(set_id);

-- ── 4. Пара «креатив × площадка» ────────────────────────────────────────────
-- Единица согласования у трафиков (они проходят каждый сайт руками на демо-кампании)
-- и единица учёта в DSP. Той же гранью ОРД принимает показы в акте — совпадение не
-- случайно: и DSP, и реестр считают по паре «материал × площадка».
CREATE TABLE IF NOT EXISTS launch_prep_pair (
    id             SERIAL PRIMARY KEY,
    -- <код сделки>-<код площадки>-<NN>, например HCLA6E-MKS-01.
    -- ВЫДАЁТСЯ В МОМЕНТ СХОЖДЕНИЯ, а не при создании: «всё до „согласовано“ стабильной
    -- парой ещё не является». Отвергнутая итерация имени не получает — поэтому в
    -- нумерации нет дыр от версий, которых не было. NN считает СРОСШИЕСЯ пары внутри
    -- размещения, а не итерации.
    code           VARCHAR(32) UNIQUE,
    set_id         INTEGER NOT NULL REFERENCES launch_prep_creative_set(id) ON DELETE CASCADE,
    target_id      INTEGER NOT NULL REFERENCES launch_prep_target(id) ON DELETE CASCADE,
    sent_at        TIMESTAMP,                     -- ушла площадке (после отмашки трафиков)
    agreed_at      TIMESTAMP,                     -- момент схождения, тогда же выдаётся code
    created_at     TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_lp_pair UNIQUE (set_id, target_id)
);
CREATE INDEX IF NOT EXISTS ix_lp_pair_set    ON launch_prep_pair(set_id);
CREATE INDEX IF NOT EXISTS ix_lp_pair_target ON launch_prep_pair(target_id);

-- ── 5. Проверка ─────────────────────────────────────────────────────────────
-- Строка заводится ПУСТОЙ в момент запроса: пустой вердикт означает «спросили, ответа
-- нет». Из этого списка берутся и знаменатель порога ЕРИД, и ответ на «кто молчит
-- третий день» для пинга. Если строка появляется только вместе с вердиктом, обе величины
-- становятся невычислимыми.
CREATE TABLE IF NOT EXISTS launch_prep_review (
    id             SERIAL PRIMARY KEY,
    set_id         INTEGER NOT NULL REFERENCES launch_prep_creative_set(id) ON DELETE CASCADE,
    -- NULL = первичная проверка комплекта целиком (она про материал, а не про получателя).
    pair_id        INTEGER REFERENCES launch_prep_pair(id) ON DELETE CASCADE,
    kind           VARCHAR(16) NOT NULL,          -- первичная_тт | трафики | площадка
    verdict        VARCHAR(16),                   -- ок | на доработку; NULL = ответа нет
    reason         TEXT,
    asked_at       TIMESTAMP NOT NULL DEFAULT now(),
    decided_at     TIMESTAMP,
    -- Снимок имени, а не ссылка на учётку: смена ответственного задним числом иначе
    -- перепишет историю согласований.
    decided_by     VARCHAR(128),
    -- авто | аккаунт | трафики | кабинет. 'авто' заведено ради первой версии, где вердикт
    -- трафиков проставляется автоматически: без отдельного значения машинная отметка через
    -- полгода неотличима от человеческой, и «эту пару никто не смотрел» уже не восстановить.
    source         VARCHAR(16) NOT NULL,
    CONSTRAINT uq_lp_review UNIQUE NULLS NOT DISTINCT (set_id, pair_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_lp_review_set  ON launch_prep_review(set_id);
CREATE INDEX IF NOT EXISTS ix_lp_review_pair ON launch_prep_review(pair_id);

-- ── 6. Причины доработки (накопитель) ───────────────────────────────────────
-- Тот же вид, что sales_publisher_kinds / sales_contact_positions / sales_document_types.
CREATE TABLE IF NOT EXISTS sales_rework_reasons (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(255) NOT NULL UNIQUE,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    is_active      BOOLEAN NOT NULL DEFAULT true
);

-- ── 7. Поля в существующих справочниках ─────────────────────────────────────
-- Постоянный короткий код площадки (MKS, DPD): средняя часть кода пары. Заполняется
-- руками один раз; при пустом коде пара не именуется.
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS code    VARCHAR(8);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_publishers_code ON sales_publishers(code)
    WHERE code IS NOT NULL;
-- ТТ отдельного поля НЕ получают: у площадки уже есть `tech_requirements` — «техрегламент ·
-- критерии к креативам», с плейсхолдером «форматы, вес, сроки подачи, запреты», правкой в
-- карточке и в сводке. Ровно то самое, и ровно на том уровне, который согласовали (одни на
-- сайт, не на поверхность). Заполнено у 0 из 41 — поэтому при первом замере пустота была
-- прочитана как «хранить негде», и первая редакция этой миграции завела дубль `tt_text`.
-- Колонка была создана и в тот же день удалена с разрешения владельца: данных в ней не
-- было ни секунды, а замороженная пустая колонка в справочнике — вечный мусор.
-- Строка ниже нужна тем, кто накатывал первую редакцию (у себя или на стенде).
ALTER TABLE sales_publishers DROP COLUMN IF EXISTS tt_text;

-- Код ККТУ: ровно ОДИН код 3-го уровня вида X.X.X из словаря ОРД (несколько допускаются
-- только для кобрендинга). Без него ЕРИД не выпустить. Живёт на бренде, потому что это
-- свойство товара, а не размещения: у одного бренда не меняется от кампании к кампании.
ALTER TABLE sales_brands ADD COLUMN IF NOT EXISTS kktu_code             VARCHAR(16);
-- Описание объекта рекламирования, 1–1000 знаков. Условно-обязательно в ОРД.
ALTER TABLE sales_brands ADD COLUMN IF NOT EXISTS ad_object_description TEXT;

-- Посадочная страница кампании: своя у каждой сделки, поэтому не на бренде.
ALTER TABLE sales_deals  ADD COLUMN IF NOT EXISTS advertiser_url        VARCHAR(512);
