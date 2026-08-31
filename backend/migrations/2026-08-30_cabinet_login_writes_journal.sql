-- Вход в кабинет попадает в журнал действий.
--
-- `pub.touch_login` — ЕДИНСТВЕННАЯ запись, которую внешний контур делает в `public`:
-- у роли `cabinet` нет права на `UPDATE`, она вызывает функцию. Строку журнала пишет
-- она же, а не отдельный вызов ядра, ровно поэтому: заводить второй канал записи
-- наружу ради одной строки означало бы расширить поверхность внешнего контура.
--
-- Запись идёт ОДНОЙ транзакцией с отметкой времени. Кабинет оборачивает вызов в
-- try/except («отметка времени не стоит того, чтобы ронять вход»), и это правило
-- распространяется на журнал: не записанный вход хуже несостоявшегося входа только на
-- бумаге.
--
-- `cabinet_id` берётся у учётки. Учётка без кабинета журнала не имеет — писать некуда,
-- и `INSERT ... SELECT` с `WHERE cabinet_id IS NOT NULL` пропускает такую строку сам.

CREATE OR REPLACE FUNCTION pub.touch_login(p_account_id integer)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $fn$
    UPDATE cabinet_account SET last_login_at = now() WHERE id = p_account_id;

    INSERT INTO cabinet_log (cabinet_id, account_id, actor_name, actor_side,
                             action, tone, created_at)
    SELECT a.cabinet_id, a.id, a.name, 'площадка', 'вход', 'info', now()
      FROM cabinet_account a
     WHERE a.id = p_account_id AND a.cabinet_id IS NOT NULL;
$fn$;

-- Право на вызов у внешней роли уже выдано прежней миграцией; повторяем на случай
-- накатывания с нуля — GRANT идемпотентен.
GRANT EXECUTE ON FUNCTION pub.touch_login(integer) TO cabinet;
