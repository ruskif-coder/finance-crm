-- Проблемные операции (владелец 20.11.2026): у операции есть то, что бухгалтеру или финансам надо разобрать руками, — и её
-- видно в реестре значком и отдельной плиткой-фильтром, а не поиском по базе. Одна строка — одна проблема; закрывается
-- либо сама (событие сняло причину), либо человеком с комментарием, как запись бэклога.
--
-- Виды на старте:
--   «пакет удалён»       — комплект УПД удалили, а операция уже оплачена или поправлена бухгалтером: её не удаляем, а помечаем;
--   «на переделке»       — документы комплекта вернули на переделку; закрывается сама повторным внесением;
--   «расхождение с 1С»   — повторное внесение дало другие сумму, НДС или № счёта, а мост оплаченную операцию не обновляет.
CREATE TABLE IF NOT EXISTS operation_issues (
    id                 SERIAL PRIMARY KEY,
    -- проблема живёт вместе с операцией: удалили операцию — проблемы больше нет
    operation_id       INTEGER NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    kind               VARCHAR(30) NOT NULL,
    -- что случилось подробно: пакет, № УПД, было → стало
    text               TEXT,
    -- комплект, из-за которого проблема; без FK намеренно — комплект как раз может быть удалён
    master_deal_upd_id INTEGER,
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    created_by         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    -- закрыта: кем, когда и что сделали; открытая — resolved_at пуст
    resolved_at        TIMESTAMP,
    resolved_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolution         TEXT
);

ALTER TABLE operation_issues DROP CONSTRAINT IF EXISTS operation_issues_kind_check;
ALTER TABLE operation_issues ADD CONSTRAINT operation_issues_kind_check
    CHECK (kind IN ('пакет удалён', 'на переделке', 'расхождение с 1С'));

-- реестр спрашивает «есть ли открытые у этих операций» на каждой странице и считает их в плитке
CREATE INDEX IF NOT EXISTS ix_operation_issues_open ON operation_issues (operation_id) WHERE resolved_at IS NULL;
