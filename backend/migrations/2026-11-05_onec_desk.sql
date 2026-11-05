-- «Документы для 1С» (владелец 05.11.2026): пока моста в 1С нет, бухгалтер сама забирает из системы данные комплекта
-- (УПД + счёт), выставляет документы в 1С и вносит обратно номера, даты, суммы и PDF. Схема согласована 05.11.2026.
-- Повторно накатываемая.

-- 1. Ответ 1С по комплекту. Уже были: onec_upd_no, onec_invoice_no, onec_invoice_date, onec_net, onec_at.
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_upd_date DATE;
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_vat DOUBLE PRECISION;
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_gross DOUBLE PRECISION;
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_by INTEGER REFERENCES users(id);
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_state VARCHAR(20);
COMMENT ON COLUMN master_deal_upds.onec_upd_date IS 'Дата УПД, выставленной в 1С';
COMMENT ON COLUMN master_deal_upds.onec_vat IS 'НДС по УПД из 1С: вернувшиеся суммы — факт, расхождение до 1 ₽ принимается';
COMMENT ON COLUMN master_deal_upds.onec_gross IS 'Сумма с НДС по УПД из 1С';
COMMENT ON COLUMN master_deal_upds.onec_by IS 'Кто внёс ответ 1С (до интеграции — бухгалтер руками)';
COMMENT ON COLUMN master_deal_upds.onec_state IS 'Где комплект у бухгалтерии: пусто — ждёт бухгалтера, «возвращён» — вернула аккаунту с комментарием, «внесён» — документы из 1С внесены';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'master_deal_upds_onec_state_check') THEN
        ALTER TABLE master_deal_upds ADD CONSTRAINT master_deal_upds_onec_state_check
            CHECK (onec_state IS NULL OR onec_state IN ('возвращён', 'внесён'));
    END IF;
END $$;

-- 2. Лента комплекта у бухгалтерии: возвраты, исправления, комментарии. Сюда же позже лягут комментарии бухгалтера из 1С
--    (правка 8 к ТЗ v2.2) с source = '1С'.
CREATE TABLE IF NOT EXISTS onec_desk_events (
    id       SERIAL PRIMARY KEY,
    upd_id   INTEGER NOT NULL REFERENCES master_deal_upds(id) ON DELETE CASCADE,
    kind     VARCHAR(20) NOT NULL CHECK (kind IN ('возврат', 'исправлено', 'комментарий', 'внесено', 'правка')),
    text     TEXT,
    source   VARCHAR(10) NOT NULL DEFAULT 'вручную',
    by_user  INTEGER REFERENCES users(id),
    at       TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_onec_desk_events_upd ON onec_desk_events (upd_id, id);
COMMENT ON TABLE onec_desk_events IS 'Что происходило с комплектом у бухгалтерии: возврат аккаунту (текст обязателен), исправлено, комментарий, внесено, правка внесённого';

-- 3. Файлы из 1С — в master_deal_files, схема не меняется: новые виды «счёт 1С», «УПД 1С», «УПД 1С xml» с upd_no.
--    Сканы подписанного читаются только по видам «скан ДС» / «скан УПД».
--    Уникальность «один файл на УПД» (2026-10-19_master_deal_scans_per_doc.sql) становится «один файл КАЖДОГО ВИДА на УПД»:
--    рядом со сканом УПД лягут PDF счёта, PDF УПД и XML из 1С. Данные не трогаются, меняется только индекс.
CREATE UNIQUE INDEX IF NOT EXISTS ux_master_files_upd_kind ON master_deal_files (master_deal_id, upd_no, kind) WHERE upd_no IS NOT NULL;
DROP INDEX IF EXISTS ux_master_files_upd;

-- 4. Роль «Бухгалтер» и право «Документы для 1С» (onec_desk: view, edit).
INSERT INTO roles (key, label, is_system, staff_group, is_master)
SELECT 'accountant', 'Бухгалтер', 0, NULL, false
 WHERE NOT EXISTS (SELECT 1 FROM roles WHERE key = 'accountant');

-- Один раз, пока у права нет ни одной строки: повтор не вернёт доступ тем, у кого его отобрали.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'onec_desk') THEN
        -- Бухгалтер — правка; Фин Менеджер и Мастер аккаунт — просмотр.
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'onec_desk', 1, 0, CASE WHEN r.key = 'accountant' THEN 1 ELSE 0 END, 0, 0, 0, 'all'
          FROM roles r
         WHERE r.key IN ('accountant', 'manager', 'role_9');
        -- Бухгалтер видит карточку мастер-сделки (без эффективности: master_deals_finance не выдаётся).
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'master_deals', 1, 0, 0, 0, 0, 0, 'all' FROM roles r
         WHERE r.key = 'accountant'
           AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = r.id AND p.section = 'master_deals');
        -- Видимость сделок «все»: без строки sales_registry область мастер-сделки отказывает 403 (sales/scope.py).
        -- Сам реестр сделок не открывается: can_view = 0.
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'sales_registry', 0, 0, 0, 0, 0, 0, 'all' FROM roles r
         WHERE r.key = 'accountant'
           AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = r.id AND p.section = 'sales_registry');
    END IF;
END $$;
