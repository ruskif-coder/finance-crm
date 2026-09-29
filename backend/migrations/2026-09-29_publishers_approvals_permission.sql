-- Право на вкладку «Согласования» раздела «Паблишеры» (dir_publishers_approvals, только
-- просмотр). Решение владельца 29.09.2026: своё право; по умолчанию видят все, кто видит
-- «Площадки». Без бэкфилла новая секция закрыта всем — отсутствие строки читается как «нельзя».
--
-- Идемпотентно: ON CONFLICT по (role_id, section).

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete)
SELECT p.role_id, 'dir_publishers_approvals', p.can_view, 0, 0, 0
FROM role_permissions p
WHERE p.section = 'dir_publishers'
ON CONFLICT (role_id, section) DO NOTHING;

SELECT r.key AS role, MAX(CASE WHEN p.section='dir_publishers' THEN p.can_view END) AS list_view,
       MAX(CASE WHEN p.section='dir_publishers_approvals' THEN p.can_view END) AS approvals_view
FROM role_permissions p JOIN roles r ON r.id = p.role_id
WHERE p.section IN ('dir_publishers', 'dir_publishers_approvals')
GROUP BY r.key ORDER BY r.key;
