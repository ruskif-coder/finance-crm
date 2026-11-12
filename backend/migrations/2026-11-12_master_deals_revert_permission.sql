-- Право «Мастер-сделки · возврат стадии» (владелец 12.11.2026). Ключ `master_deals_revert` неизменяем; admin может всегда
-- (в role_permissions не представлен). До этого назад на шаг мог админ или роль с отметкой «мастер» — бэкфилл сохраняет это
-- поведение там, где оно имело смысл: роли «мастер», у которых есть правка мастер-сделок. Один раз, пока строк права нет.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'master_deals_revert') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'master_deals_revert', 1, 0, 1, 0, 0, 0, 'all'
          FROM roles r JOIN role_permissions p ON p.role_id = r.id AND p.section = 'master_deals' AND p.can_edit = 1
         WHERE r.is_master;
    END IF;
END $$;
