-- Защита входа во внешний контур: блокировка после серии неудачных попыток.
--
-- До 30.08.2026 кабинет был защищён от ПЕРЕЧИСЛЕНИЯ учёток (одинаковый ответ и прогон
-- bcrypt даже для несуществующего адреса), но не от ПЕРЕБОРА пароля. Для внешнего
-- контура это хуже, чем для внутреннего: туда ходят не наши сотрудники, адрес входа
-- известен площадке, а учётка одна на весь кабинет.
--
-- Своей таблицы попыток НЕ ЗАВОДИМ. Правило блокировки уже реализовано в ядре
-- (`app/routers/auth.py`: 5 попыток, 15 минут) и стоит на таблице `login_attempts` —
-- вторая реализация того же однажды разойдётся с первой, и разойдётся молча: кто-то
-- поменяет порог в одном месте. Поэтому кабинет получает ДОСТУП К ТОМУ ЖЕ СЧЁТЧИКУ
-- через функции `pub.*`, как и с `pub.touch_login`.
--
-- Почты двух контуров не пересекаются (замер 30.08.2026: 0 совпадений между `users` и
-- `cabinet_account`), поэтому общий счётчик не смешивает разных людей. Побочная польза:
-- перебор по обоим контурам виден в одном месте.
--
-- SECURITY DEFINER + SET search_path — не гигиена, а часть защиты: без явного пути
-- вызывающий может подставить свою схему и увести вызов на свою таблицу.

CREATE OR REPLACE FUNCTION pub.login_lock_minutes(p_email text)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    -- Сколько минут осталось до снятия блокировки. 0 — не заблокирован.
    SELECT coalesce(
        (SELECT ceil(extract(epoch FROM (locked_until - now())) / 60)::int
         FROM login_attempts
         WHERE lower(email) = lower(p_email) AND locked_until > now()
         LIMIT 1), 0);
$$;

CREATE OR REPLACE FUNCTION pub.register_failed_login(p_email text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    -- Те же числа, что в ядре. Меняя их, менять в обоих местах — или, лучше, вынести
    -- в одну таблицу настроек, когда появится третий потребитель.
    max_attempts constant int := 5;
    lock_minutes constant int := 15;
    cur int;
BEGIN
    INSERT INTO login_attempts (email, failed_count, updated_at)
    VALUES (lower(p_email), 1, now())
    ON CONFLICT DO NOTHING;

    UPDATE login_attempts
       SET failed_count = failed_count + 1, updated_at = now()
     WHERE lower(email) = lower(p_email)
     RETURNING failed_count INTO cur;

    IF cur IS NOT NULL AND cur >= max_attempts THEN
        UPDATE login_attempts
           SET locked_until = now() + make_interval(mins => lock_minutes),
               failed_count = 0
         WHERE lower(email) = lower(p_email);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION pub.clear_login_attempts(p_email text)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    DELETE FROM login_attempts WHERE lower(email) = lower(p_email);
$$;

-- Роль внешнего контура получает ТОЛЬКО право выполнить эти три функции. Прав на саму
-- `login_attempts` у неё нет и не появляется: она по-прежнему не видит `public`.
GRANT EXECUTE ON FUNCTION pub.login_lock_minutes(text)   TO cabinet;
GRANT EXECUTE ON FUNCTION pub.register_failed_login(text) TO cabinet;
GRANT EXECUTE ON FUNCTION pub.clear_login_attempts(text)  TO cabinet;
