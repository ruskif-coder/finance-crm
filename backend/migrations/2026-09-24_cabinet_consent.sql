-- Согласие на обработку персональных данных в кабинете паблишера (владелец, 24.09.2026).
--
-- Как у сотрудников (`users.consent_accepted_at`): при первом входе человек видит
-- политику и согласие и принимает их; без этого кабинет не отдаёт ни одних данных.
-- Проверку держит сервер кабинета, а не экран: экран обходится прямым вызовом API.
--
-- Состав согласован с владельцем 24.09.2026: одно поле — момент принятия. Пусто —
-- согласие не дано. Версии текста нет (решение владельца): при смене текста повторное
-- принятие заводится отдельно.

ALTER TABLE cabinet_account ADD COLUMN IF NOT EXISTS consent_accepted_at timestamp;

COMMENT ON COLUMN cabinet_account.consent_accepted_at IS
    'Момент принятия согласия на обработку ПДн (152-ФЗ) в кабинете паблишера; пусто — не принято';

-- Кабинет читает учётку только через представление. Новая колонка — В КОНЕЦ: `CREATE OR
-- REPLACE VIEW` не даёт менять порядок и состав прежних колонок.
CREATE OR REPLACE VIEW pub.account_v1 WITH (security_barrier) AS
SELECT a.id, a.email, a.name, a.hashed_password, a.is_active, a.can_approve,
       a.consent_accepted_at
FROM cabinet_account a;

GRANT SELECT ON pub.account_v1 TO cabinet;

-- Принятие — через функцию ядра, как отметка входа (`pub.touch_login`): у роли
-- `cabinet` нет права на `UPDATE`, и заводить его ради одного поля значило бы расширить
-- поверхность внешнего контура. Повторный вызов момент НЕ сдвигает (coalesce): первое
-- принятие и есть юридически значимое. Строка журнала — только при первом принятии.
CREATE OR REPLACE FUNCTION pub.accept_consent(p_account_id integer)
RETURNS timestamp
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $fn$
DECLARE
    was timestamp;
    now_at timestamp;
BEGIN
    SELECT consent_accepted_at INTO was FROM cabinet_account WHERE id = p_account_id;
    IF was IS NOT NULL THEN
        RETURN was;
    END IF;
    now_at := now() AT TIME ZONE 'UTC';
    UPDATE cabinet_account SET consent_accepted_at = now_at WHERE id = p_account_id;

    INSERT INTO cabinet_log (cabinet_id, account_id, actor_name, actor_side,
                             action, tone, created_at)
    SELECT a.cabinet_id, a.id, a.name, 'площадка', 'согласие_пдн', 'info', now()
      FROM cabinet_account a
     WHERE a.id = p_account_id AND a.cabinet_id IS NOT NULL;
    RETURN now_at;
END
$fn$;

REVOKE ALL ON FUNCTION pub.accept_consent(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pub.accept_consent(integer) TO cabinet;
