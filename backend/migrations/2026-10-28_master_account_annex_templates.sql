-- «Мастер аккаунт» (role_9) добавляет шаблоны ДС договора и правит их в конструкторе — как юрист (владелец 28.10.2026).
-- Право `annex_templates`: create + edit. Один раз: отметка в company_settings, чтобы повторный накат не вернул право, если его потом
-- снимут галочкой в «Ролях». Роль ищется по ключу и названию — на чужой базе с другим набором ролей ничего не делает.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM company_settings WHERE key = 'migration:2026-10-28_master_account_annex_templates') THEN
        UPDATE role_permissions rp SET can_view = 1, can_create = 1, can_edit = 1
          FROM roles r
         WHERE r.id = rp.role_id AND r.key = 'role_9' AND r.label = 'Мастер аккаунт' AND rp.section = 'annex_templates';
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete)
        SELECT r.id, 'annex_templates', 1, 1, 1, 0 FROM roles r
         WHERE r.key = 'role_9' AND r.label = 'Мастер аккаунт'
           AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.section = 'annex_templates');
        INSERT INTO company_settings (key, value) VALUES ('migration:2026-10-28_master_account_annex_templates', 'applied');
    END IF;
END $$;
