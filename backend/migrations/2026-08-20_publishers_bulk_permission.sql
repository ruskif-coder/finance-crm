-- Отдельное право на экран «Заполнение» (dir_publishers_bulk, только просмотр).
--
-- Ключ права неизменяем, поэтому заводится один раз и навсегда. Само по себе
-- появление ключа в SECTIONS ничего не даёт живым ролям: строки в role_permissions
-- создаются только при сохранении роли, а отсутствие строки читается как «нельзя».
-- Значит без бэкфилла тот, кто вчера пользовался «Заполнением», сегодня перестал бы
-- его видеть — молча, без ошибки.
--
-- Поэтому переносим ровно то, что было: кто видел «Площадки», тот видит и
-- «Заполнение». Правку экран по-прежнему берёт из dir_publishers.edit — bulk ходит
-- в те же эндпоинты, что и карточка, отдельного can_edit у него нет.
--
-- Идемпотентно: ON CONFLICT по (role_id, section) — можно накатывать повторно.

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete)
SELECT p.role_id, 'dir_publishers_bulk', p.can_view, 0, 0, 0
FROM role_permissions p
WHERE p.section = 'dir_publishers'
ON CONFLICT (role_id, section) DO NOTHING;

-- Проверка: у каждой роли с доступом к площадкам должна появиться парная строка.
SELECT r.key AS role, MAX(CASE WHEN p.section='dir_publishers' THEN p.can_view END) AS list_view,
       MAX(CASE WHEN p.section='dir_publishers_bulk' THEN p.can_view END) AS bulk_view
FROM role_permissions p JOIN roles r ON r.id = p.role_id
WHERE p.section IN ('dir_publishers', 'dir_publishers_bulk')
GROUP BY r.key ORDER BY r.key;
