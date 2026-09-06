-- Экран «Добавить данные» (/directory/add) — своя секция прав `directory_add`.
--
-- До 06.09.2026 пункт меню был подвешен на право «Контрагенты» (`counterparties`). Экран
-- при этом в конструкторе ролей не показывался вовсе: матрица строится из SECTIONS, и
-- раздела без своего ключа в ней просто нет — настроить доступ было НЕЛЬЗЯ, а не «пока
-- не настроили».
--
-- Действие ровно одно — `can_view`, то есть «пускать ли на экран». Своих ручек экран не
-- завёл: он зовёт существующие, и каждая спрашивает своё право (counterparties · edit,
-- contracts · edit, dir_* · edit). Блок без права гасится прямо на экране. Поэтому
-- `can_edit` здесь не заводится — он ничего бы не открыл.
--
-- Бэкфилл копирует ровно прежнее поведение: экран видит тот, кто видел его до сих пор,
-- то есть у кого есть просмотр контрагентов.
--
-- Роль admin в role_permissions не представлена: её права синтезируются как все-истина.
-- Повторный прогон безопасен: вставка идёт только там, где строки ещё нет.

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit,
                              can_delete, can_view_operations, can_approve, deals_scope)
SELECT rp.role_id, 'directory_add',
       COALESCE(rp.can_view, 0),
       0, 0, 0, 0, 0, COALESCE(rp.deals_scope, 'all')
  FROM role_permissions rp
 WHERE rp.section = 'counterparties'
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = rp.role_id AND x.section = 'directory_add');
