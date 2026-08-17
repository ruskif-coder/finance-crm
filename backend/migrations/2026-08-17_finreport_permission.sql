-- Своё право на «Фин. отчёт»: до сих пор экран висел на праве P&L (`pl`), то есть выдать
-- отчёт без P&L или наоборот было нельзя. Согласовано с владельцем 2026-08-17.
--
-- Ключ права неизменяем (он записан в role_permissions у живых пользователей), поэтому
-- заводится новый — `finreport`, а не переименовывается существующий.
--
-- Бэкфилл: право копируется с `pl`. Без него роли, у которых доступ к отчёту был,
-- потеряли бы его молча в момент выкладки кода — новая секция по умолчанию запрещена.
-- Роль admin в role_permissions не представлена вовсе (её права синтезируются как
-- «всё разрешено»), поэтому её тут нет и быть не должно.

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                              can_view_operations, can_approve, deals_scope)
SELECT rp.role_id, 'finreport', rp.can_view, 0, 0, 0, 0, 0, 'all'
  FROM role_permissions rp
 WHERE rp.section = 'pl'
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = rp.role_id AND x.section = 'finreport');
