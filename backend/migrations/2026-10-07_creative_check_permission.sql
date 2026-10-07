-- Право на «Проверку креатива» (аккаунты). Ключ `creative_check` неизменяем.
-- По умолчанию доступ получают аккаунты (владелец 07.10.2026): роли, у которых есть дашборд аккаунта —
-- с правкой (загрузка/нацеливание) и удалением, если и в дашборде у них правка; роли только с просмотром
-- дашборда — просмотр. Роль admin в role_permissions не представлена (права синтезируются).
-- Повторный накат ничего не меняет: строка заводится один раз на роль.

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                              can_view_operations, can_approve, deals_scope)
SELECT rp.role_id, 'creative_check', 1, 0, rp.can_edit, rp.can_edit, 0, 0, 'all'
  FROM role_permissions rp
 WHERE rp.section = 'accounts_dashboard' AND rp.can_view = 1
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = rp.role_id AND x.section = 'creative_check');
