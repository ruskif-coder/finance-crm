-- Общий каталог должностей контактных лиц (2026-08-19).
--
-- Должность вводится в карточке площадки, но каталог один на всех: «аккаунт»,
-- «техподдержка», «бухгалтерия» повторяются у каждой площадки, и свободный ввод
-- через месяц даст «Аккаунт», «аккаунт-менеджер» и «акк» как три разные должности.
-- Устроено как накопитель видов паблишера и чипы таргетинга: список пополняется вводом,
-- отдельного раздела меню под него нет.
--
-- Не FK: переименование должности не должно осиротить контакт, а связь тут
-- справочная, а не структурная (тот же приём, что sales_publishers.kind).
CREATE TABLE IF NOT EXISTS sales_contact_positions (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- Засев тем, что уже введено в контактах площадок: каталог не должен начинаться пустым,
-- когда значения фактически есть.
INSERT INTO sales_contact_positions (name, sort_order)
SELECT DISTINCT btrim(role), 100
  FROM sales_publisher_contacts
 WHERE role IS NOT NULL AND btrim(role) <> ''
ON CONFLICT (name) DO NOTHING;
