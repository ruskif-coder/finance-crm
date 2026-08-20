-- Паблишеры, третья правка (2026-08-19): то, что требует дизайн-хендофф
-- «Справочник паблишеров и карточка паблишера» (docs/паблишеры.zip).

-- ---------------------------------------------------------------- площадка
-- Часовой пояс. Звонок в 8 утра по Москве во владивостокскую аптеку приходится на
-- конец их рабочего дня. Храним смещение в часах от МСК (перехода на летнее время в
-- России нет, зона IANA избыточна).
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS timezone_offset INTEGER NOT NULL DEFAULT 0;

-- «Код наш» — самостоятельная отметка для справки. Намеренно НЕ вычисляется из статусов
-- поверхностей: вычисляемая и проставленная руками правда об одном и том же расходятся.
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS our_code BOOLEAN NOT NULL DEFAULT FALSE;

-- Делится ли площадка данными. Меняет доступные механики Альфарм-Таргета, поэтому
-- выводится тегом DATA / NO DATA прямо на плашке услуги. Атрибут площадки, не связки.
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS shares_data BOOLEAN NOT NULL DEFAULT FALSE;

-- Техрегламент: форматы, вес, сроки подачи креативов, запреты. Влияет на дедлайны
-- производства, поэтому у подключённых площадок его отсутствие — повод для отчёта.
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS tech_requirements TEXT;

-- Медиакит. Храним последнюю версию: загрузка заменяет предыдущую (решение владельца).
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS media_kit_filename VARCHAR;
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS media_kit_path VARCHAR;
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS media_kit_uploaded_at TIMESTAMP;

-- УСТАРЕЛО: приоритезация — услуга каталога, а не признак площадки (в sales_services
-- она есть отдельной строкой). Колонка не удаляется, код её больше не читает;
-- проставленные «ДА» перенесены в sales_publisher_services скриптом миграции данных.
COMMENT ON COLUMN sales_publishers.is_priority IS 'УСТАРЕЛО с 2026-08-19: приоритезация ведётся услугой каталога';

-- ---------------------------------------------------------------- платформы приложения
-- APP не монолит: Android бывает подключён, когда iOS ещё в подготовке. Услуги
-- отмечаются на поверхности (прайс общий), а трафик считается по платформам отдельно —
-- иначе закупку не спланировать.
CREATE TABLE IF NOT EXISTS sales_publisher_surface_platforms (
    id         SERIAL PRIMARY KEY,
    surface_id INTEGER NOT NULL REFERENCES sales_publisher_surfaces(id) ON DELETE CASCADE,
    kind       VARCHAR NOT NULL,          -- android | ios
    integration_status VARCHAR NOT NULL DEFAULT 'НЕТ',
    is_active  BOOLEAN NOT NULL DEFAULT FALSE,   -- работаем ли мы с платформой
    note       TEXT,
    CONSTRAINT uq_surface_platform UNIQUE (surface_id, kind)
);

-- ---------------------------------------------------------------- замеры трафика
-- Не поля карточки, а замеры на дату: в исходной таблице цифры записаны текстом
-- вперемешку («900 тыс», «2,05 млн», «84 811 тыс») и означают факт конкретного периода.
-- Один замер на месяц и показатель: повторный ввод исправляет опечатку, а не плодит
-- вторую точку за тот же месяц (решение владельца).
CREATE TABLE IF NOT EXISTS sales_publisher_traffic (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    scope        VARCHAR NOT NULL,     -- web | app_android | app_ios | ad_requests
    value        DOUBLE PRECISION,
    -- Глубина просмотра, страниц на визит. У запросов рекламного кода её нет — NULL.
    depth        DOUBLE PRECISION,
    measured_at  DATE NOT NULL,        -- первое число месяца замера
    source       VARCHAR NOT NULL DEFAULT 'manual',   -- manual | adfox | analytics
    CONSTRAINT uq_publisher_traffic UNIQUE (publisher_id, scope, measured_at)
);

CREATE INDEX IF NOT EXISTS ix_publisher_traffic_pub ON sales_publisher_traffic (publisher_id);

-- ---------------------------------------------------------------- договоры
-- Источник документа: файл в системе или ссылка на ЭДО. От него зависит, куда ведёт
-- кнопка рядом с номером и предлагать ли загрузку.
ALTER TABLE sales_publisher_contracts ADD COLUMN IF NOT EXISTS document_source VARCHAR;   -- file | edo
ALTER TABLE sales_publisher_contracts ADD COLUMN IF NOT EXISTS document_url VARCHAR;
ALTER TABLE sales_publisher_contracts ADD COLUMN IF NOT EXISTS document_filename VARCHAR;
ALTER TABLE sales_publisher_contracts ADD COLUMN IF NOT EXISTS document_path VARCHAR;

-- ---------------------------------------------------------------- контакты
-- MAX равноправен телеграму: часть площадок с телеграма уходит, период двух
-- мессенджеров идёт сейчас. Должность ложится в существующее role.
ALTER TABLE sales_publisher_contacts ADD COLUMN IF NOT EXISTS max_url VARCHAR;
