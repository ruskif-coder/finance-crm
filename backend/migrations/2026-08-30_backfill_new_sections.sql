-- Раздача двух секций, заведённых на неделе и не доставшихся никому.
--
-- Замер 30.08.2026: `creatives` и `dir_publishers_cabinets` объявлены в `SECTIONS`, но
-- строк в `role_permissions` у них ноль. Новая секция по умолчанию ЗАПРЕЩЕНА всем, и
-- проходил её только `admin` — он обходит проверки безусловно. То есть аккаунт, который
-- должен собирать комплекты креативов, физически не мог этого делать, а выглядело это
-- как «у меня почему-то нет доступа».
--
-- Ровно тот случай, ради которого в навыке записано «с новым разделом сразу спрашивать
-- про роли»: секция без бэкфилла — не «настроим позже», а «не работает ни у кого».
--
-- Состав согласован владельцем 30.08.2026.

-- ── Креативы: аккаунт собирает, сейлз смотрит ────────────────────────────────
--
-- Полный набор (view+edit+approve) у аккаунтов: они собирают комплекты и записывают
-- вердикт площадки с её слов. Сейлзам — только просмотр: материал не их зона, но видеть,
-- что происходит с креативами своей сделки, они должны, иначе каждый вопрос идёт через
-- аккаунта.
-- Порядок колонок: view, create, edit, delete, approve. Первая версия этой миграции
-- поставила единицу в `can_delete` вместо `can_approve` — то есть выдала действие,
-- которого у секции нет вовсе (объявлены view/edit/approve), и не выдала то, ради
-- которого раздача затевалась. Молча: лишний флаг ничего не открывает, а нехватка
-- выглядит как «у меня нет прав».
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete, can_approve)
SELECT r.id, 'creatives', 1, 0, 1, 0, 1
FROM roles r WHERE r.id IN (8, 9)
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.section = 'creatives');

-- Приведение уже созданных строк — миграция обязана быть повторно накатываемой, а
-- первая версия успела отработать.
UPDATE role_permissions SET can_edit = 1, can_delete = 0, can_approve = 1
 WHERE section = 'creatives' AND role_id IN (8, 9);

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete, can_approve)
SELECT r.id, 'creatives', 1, 0, 0, 0, 0
FROM roles r WHERE r.id IN (5, 7)
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.section = 'creatives');

-- ── Кабинеты паблишеров ──────────────────────────────────────────────────────
--
-- Менеджер паблишеров — хозяин зоны: он заводит кабинеты, контакты и выдаёт учётки.
-- Мастер аккаунт — второй, чтобы выдача доступа не вставала, когда менеджер недоступен.
-- Больше никому: учётка в кабинете — это доступ к нашим креативам ДО старта, и раздавать
-- его должен тот, кто отвечает за утечку.
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete, can_approve)
SELECT r.id, 'dir_publishers_cabinets', 1, 1, 1, 0, 0
FROM roles r WHERE r.id IN (9, 10)
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.section = 'dir_publishers_cabinets');
