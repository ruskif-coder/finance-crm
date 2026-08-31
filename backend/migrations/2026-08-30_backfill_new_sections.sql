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
--
-- ── Почему роли ищутся по `label`, а не по id (правка 31.08.2026) ────────────
--
-- Первая редакция брала роли литералами: `r.id IN (8, 9)`, `(5, 7)`, `(9, 10)`. На стенде
-- это Аккаунт / Мастер аккаунт / Сейлз / Мастер Сейлз / Менеджер паблишеров, но id ролей
-- — это данные конкретной базы, а не свойство системы: на проде их девять против восьми
-- локальных (замер 23.08.2026), и совпадение нумерации ничем не гарантировано.
--
-- Цена ошибки несимметрична. Промах по `label` не выдаёт прав никому — заметно сразу:
-- человек говорит «у меня нет раздела». Промах по id выдаёт права ЧУЖОЙ роли — и это не
-- видно вообще: доступ к креативам до старта РК оказывается у того, кому его не давали.
--
-- Соседние миграции прав (`2026-08-25_ord_permissions.sql`, `2026-08-28_traffic_queue.sql`)
-- всегда искали по `label`; эта одна выбивалась.
--
-- Чтобы промах по имени не был молчаливым, в конце файла стоит сводка: она печатает,
-- какие роли что получили. Читать её обязательно — пустая строка означает, что роль с
-- таким названием на этой базе не нашлась.

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
FROM roles r WHERE r.label IN ('Аккаунт', 'Мастер аккаунт')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.section = 'creatives');

-- Приведение строк, созданных первой (ошибочной) редакцией: у них `can_delete = 1` и
-- `can_approve = 0`. Условие по этой паре флагов обязательно — без него UPDATE затирал бы
-- и то, что владелец мог поправить руками в конструкторе ролей.
UPDATE role_permissions SET can_edit = 1, can_delete = 0, can_approve = 1
 WHERE section = 'creatives' AND can_delete = 1 AND can_approve = 0
   AND role_id IN (SELECT id FROM roles WHERE label IN ('Аккаунт', 'Мастер аккаунт'));

INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete, can_approve)
SELECT r.id, 'creatives', 1, 0, 0, 0, 0
FROM roles r WHERE r.label IN ('Сейлз', 'Мастер Сейлз')
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
FROM roles r WHERE r.label IN ('Мастер аккаунт', 'Менеджер паблишеров')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.section = 'dir_publishers_cabinets');

-- ── Сводка: что реально роздано ──────────────────────────────────────────────
--
-- Молчаливый промах по имени роли — единственный оставшийся способ этой миграции
-- ошибиться. Печатаем результат, чтобы он был виден тому, кто накатывает, а не
-- обнаруживался через неделю по жалобе «у меня нет раздела».
DO $$
DECLARE
    rec record;
BEGIN
    RAISE NOTICE '── Раздано прав по секциям ──';
    FOR rec IN
        SELECT rp.section, string_agg(r.label, ', ' ORDER BY r.label) AS roles
          FROM role_permissions rp JOIN roles r ON r.id = rp.role_id
         WHERE rp.section IN ('creatives', 'dir_publishers_cabinets')
         GROUP BY rp.section ORDER BY rp.section
    LOOP
        RAISE NOTICE '  % → %', rec.section, rec.roles;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM role_permissions
                    WHERE section IN ('creatives', 'dir_publishers_cabinets')) THEN
        RAISE WARNING 'НИ ОДНА роль не получила прав — проверьте названия ролей в таблице roles';
    END IF;
END $$;
