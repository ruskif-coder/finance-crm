-- Два права под обвязку ОРД. Согласовано с владельцем 25.08.2026.
--
-- Новая секция по умолчанию ЗАПРЕЩЕНА всем, поэтому без бэкфилла экран справочника
-- окажется недоступен даже тем, кто должен им пользоваться. Роль admin в
-- role_permissions не представлена вовсе (её права синтезируются как «всё разрешено»),
-- поэтому её здесь нет и быть не должно.
--
-- Раскладка: ОРД — зона аккаунта, он же заводит недостающее. Сейлзам достаточно
-- смотреть справочник. Остальным ролям право не выдаётся.

-- Аккаунт и Мастер аккаунт: полный доступ к справочнику и право отправки.
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                              can_view_operations, can_approve, deals_scope)
SELECT r.id, 'ord', 1, 0, 1, 0, 0, 0, 'all'
  FROM roles r
 WHERE r.label IN ('Аккаунт', 'Мастер аккаунт')
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = r.id AND x.section = 'ord');

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                              can_view_operations, can_approve, deals_scope)
SELECT r.id, 'ord_submit', 1, 1, 0, 0, 0, 0, 'all'
  FROM roles r
 WHERE r.label IN ('Аккаунт', 'Мастер аккаунт')
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = r.id AND x.section = 'ord_submit');

-- Сейлз и Мастер Сейлз: только смотреть справочник.
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                              can_view_operations, can_approve, deals_scope)
SELECT r.id, 'ord', 1, 0, 0, 0, 0, 0, 'all'
  FROM roles r
 WHERE r.label IN ('Сейлз', 'Мастер Сейлз')
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = r.id AND x.section = 'ord');
