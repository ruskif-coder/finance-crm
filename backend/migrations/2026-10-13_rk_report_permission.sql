-- Право на «Отчёт по РК». Ключ `rk_report` неизменяем. Роль admin в role_permissions не представлена.
-- До 13.10.2026 экран открывался по праву дашборда трафика, поэтому роли с его просмотром получают просмотр
-- нового права — доступ не пропадает. Остальным (в том числе аккаунтам) выдаёт владелец в настройках ролей.
-- Бэкфилл — один раз, пока у права нет ни одной строки: повтор не вернёт доступ тем, у кого его отобрали.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'rk_report') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT rp.role_id, 'rk_report', 1, 0, 0, 0, 0, 0, 'all'
          FROM role_permissions rp
         WHERE rp.section = 'traffic_dashboard' AND rp.can_view = 1;
    END IF;
END $$;
