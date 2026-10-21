-- Право «Эффективность мастер-сделок» (владелец 19.10.2026): прибыль, маржа и себестоимость пакета. Только просмотр.
-- Ключ `master_deals_finance` неизменяем; admin видит всегда (в role_permissions не представлен).
-- Бэкфилл по решению владельца: Фин Менеджер (manager), Мастер аккаунт (role_9). Один раз, пока строк права нет.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'master_deals_finance') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'master_deals_finance', 1, 0, 0, 0, 0, 0, 'all' FROM roles r WHERE r.key IN ('manager', 'role_9');
    END IF;
END $$;
