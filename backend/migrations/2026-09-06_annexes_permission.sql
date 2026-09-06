-- Приложения к договорам (ДС) — своя секция прав.
--
-- До 06.09.2026 экран сидел на праве «Договоры» (`contracts`). Это неверно по существу:
-- реестр приложений показывает суммы сделок и выпускает клиенту документы, а карточку
-- договора правит и тот, кому этих сумм знать не нужно.
--
-- Новая секция по умолчанию ЗАПРЕЩЕНА ВСЕМ: матрица ролей строится из SECTIONS, и без
-- бэкфилла экран пропал бы у тех, у кого он был. Поэтому право копируется с договоров:
--   can_view   ← contracts.can_view
--   can_edit   ← contracts.can_edit
--   can_create ← contracts.can_edit   (завести черновик — то же по весу, что правка)
--
-- Роль admin в role_permissions не представлена вовсе: её права синтезируются как
-- все-истина, поэтому её здесь и не должно быть.
--
-- Хранение — строка на пару (роль, секция) с колонками can_*, а НЕ строка на действие.
-- Повторный прогон безопасен: вставка идёт только там, где строки ещё нет.

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit,
                              can_delete, can_view_operations, can_approve, deals_scope)
SELECT rp.role_id, 'annexes',
       COALESCE(rp.can_view, 0),
       COALESCE(rp.can_edit, 0),
       COALESCE(rp.can_edit, 0),
       0, 0, 0, COALESCE(rp.deals_scope, 'all')
  FROM role_permissions rp
 WHERE rp.section = 'contracts'
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = rp.role_id AND x.section = 'annexes');
