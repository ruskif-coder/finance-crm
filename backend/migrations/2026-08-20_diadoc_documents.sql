-- Реестр документов Диадока и их связь с операциями.
-- Согласовано с владельцем 2026-08-20.
--
-- Зачем отдельный реестр, а не поле-ссылка в операции:
--   * у одной операции законно бывает несколько документов (пакет ДС + УПД + Счёт),
--     и каждый показывается своей иконкой;
--   * один счёт может закрываться двумя платежами, то есть двумя операциями;
--   * повторная загрузка того же файла не должна плодить дубли — за это отвечает
--     уникальный document_id;
--   * надо видеть, ЧЕМ подтверждена привязка, иначе неразличимы «совпал номер счёта»
--     и «совпала сумма в окне 180 дней», а доверие к ним разное.
--
-- Operation.document_link НЕ трогается: там лежат 660 ссылок на входящие документы,
-- проставленных вручную. Реестр живёт рядом, ручная разметка остаётся источником правды.

CREATE TABLE IF NOT EXISTS diadoc_documents (
    id                  SERIAL PRIMARY KEY,

    -- Тройка идентификаторов из ссылки вида
    -- https://diadoc.kontur.ru/{box_id}/Document/Show?letterId={letter_id}&documentId={document_id}
    -- document_id уникален: это и есть ключ идемпотентности повторного импорта.
    box_id              VARCHAR NOT NULL,
    letter_id           VARCHAR NOT NULL,
    document_id         VARCHAR NOT NULL UNIQUE,

    -- Тип берётся из колонки «Имя файла» выгрузки: Счет / УПД / ДС.
    doc_type            VARCHAR NOT NULL DEFAULT 'Счет',
    -- Направление в выгрузке Диадока НЕ указано — задаётся при импорте.
    direction           VARCHAR NOT NULL DEFAULT 'outgoing',

    -- number_norm — номер без «№», пробелов и ведущих нулей; матч идёт по нему,
    -- потому что в базе номера записаны свободно («12», «000012», «№12»).
    number              VARCHAR,
    number_norm         VARCHAR,
    doc_date            DATE,

    -- Суммы служат контролем совпадения, а не ключом: встречаются документы,
    -- где номер и дата те же, а сумма отличается.
    total               DOUBLE PRECISION,
    vat                 DOUBLE PRECISION,

    counterparty_inn    VARCHAR,
    counterparty_kpp    VARCHAR,
    counterparty_name   VARCHAR,
    -- Мягкая связь: документ загружается и тогда, когда контрагента в справочнике нет.
    counterparty_id     INTEGER REFERENCES counterparties(id) ON DELETE SET NULL,

    -- Статус документооборота дословно, по-русски, как в выгрузке.
    status              VARCHAR,
    file_name           VARCHAR,
    link                VARCHAR,
    comment             VARCHAR,

    imported_at         TIMESTAMP DEFAULT now(),
    imported_by         INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_diadoc_inn_number ON diadoc_documents (counterparty_inn, number_norm);
CREATE INDEX IF NOT EXISTS idx_diadoc_doc_date   ON diadoc_documents (doc_date);
CREATE INDEX IF NOT EXISTS idx_diadoc_type_dir   ON diadoc_documents (doc_type, direction);
CREATE INDEX IF NOT EXISTS idx_diadoc_cp         ON diadoc_documents (counterparty_id);

CREATE TABLE IF NOT EXISTS operation_documents (
    id              SERIAL PRIMARY KEY,
    operation_id    INTEGER NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    document_id     INTEGER NOT NULL REFERENCES diadoc_documents(id) ON DELETE CASCADE,

    -- Чем подтверждена привязка. Значения: number_date | number | amount_window | manual.
    -- Нужно, чтобы позже отличить надёжную привязку от предположения.
    match_rule      VARCHAR NOT NULL DEFAULT 'manual',
    -- Расхождение суммы документа и операции на момент привязки; NULL — сошлось.
    amount_mismatch DOUBLE PRECISION,

    matched_by      INTEGER REFERENCES users(id),
    matched_at      TIMESTAMP DEFAULT now(),

    CONSTRAINT uq_operation_document UNIQUE (operation_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_opdoc_operation ON operation_documents (operation_id);
CREATE INDEX IF NOT EXISTS idx_opdoc_document  ON operation_documents (document_id);
