-- Право «Мастер-сделки» (владелец 19.10.2026): реестр пакетов закрытия в «Финансах» и карточка пакета.
-- Уровни нет / просмотр / редактирование (view, edit). Ключ `master_deals` неизменяем. Роль admin в role_permissions не представлена.
-- До этого карточка пакета шла по праву реестра сделок — бэкфилл по решению владельца:
--   Аккаунт (role_8), Мастер аккаунт (role_9) — редактирование: они собирают пакет;
--   Фин Менеджер (manager), Юрист (role_6) — просмотр. Сейлзам и трафику — нет.
-- Один раз, пока у права нет ни одной строки: повтор не вернёт доступ тем, у кого его отобрали.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'master_deals') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'master_deals', 1, 0, CASE WHEN r.key IN ('role_8', 'role_9') THEN 1 ELSE 0 END, 0, 0, 0, 'all'
          FROM roles r
         WHERE r.key IN ('role_8', 'role_9', 'manager', 'role_6');
    END IF;
END $$;
