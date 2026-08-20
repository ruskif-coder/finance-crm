-- Документы площадки и архив договора (2026-08-19).

-- 1. Договор не удаляется, а уходит в архив: по нему шли деньги, и исчезновение из
--    карточки означало бы, что договора не существовало. Тот же приём, что мягкое
--    удаление в справочниках.
ALTER TABLE sales_publisher_contracts ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Каталог типов документов. Пополняется вводом из формы загрузки — отдельного
--    раздела меню под него нет, как под должности контактов и виды паблишеров.
CREATE TABLE IF NOT EXISTS sales_document_types (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

INSERT INTO sales_document_types (name, sort_order) VALUES
    ('Медиакит', 10),
    ('ТТ на баннеры', 20),
    ('Доп. инструкции', 30)
ON CONFLICT (name) DO NOTHING;

-- 3. Документы площадки. Медиакит становится одним из типов, а не отдельным полем:
--    иначе каждый новый вид файла требовал бы своей тройки колонок.
CREATE TABLE IF NOT EXISTS sales_publisher_documents (
    id           SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    -- Имя типа из sales_document_types, не FK: переименование типа не должно
    -- осиротить файл (тот же приём, что sales_publishers.kind).
    doc_type     VARCHAR NOT NULL,
    filename     VARCHAR NOT NULL,   -- имя на диске, с префиксом id
    path         VARCHAR,
    uploaded_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    uploaded_by  INTEGER REFERENCES users(id),
    note         TEXT
);

CREATE INDEX IF NOT EXISTS ix_publisher_documents_pub ON sales_publisher_documents (publisher_id);

-- УСТАРЕЛО: медиакит одним полем на площадку. Колонки заморожены, код их не читает —
-- файлы живут в sales_publisher_documents с типом «Медиакит».
COMMENT ON COLUMN sales_publishers.media_kit_filename IS 'УСТАРЕЛО с 2026-08-19: см. sales_publisher_documents';
