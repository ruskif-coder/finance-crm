-- Счётчик неудачных входов кабинета получает свою область.
--
-- НАЙДЕНО 31.08.2026 при разборе безопасности внешнего контура. Кабинет вёл попытки в
-- ТОЙ ЖЕ строке `login_attempts`, что и ядро, — это было сделано намеренно (миграция
-- 2026-08-30_cabinet_login_lockout.sql, «вторая реализация правила разойдётся с первой»),
-- и обоснование опиралось на замер: почты двух контуров не пересекаются, 0 совпадений
-- между `users` и `cabinet_account`.
--
-- Замер верный, вывод — нет. Пересекаются не УЧЁТКИ, а СТРОКИ: `POST /api/login` кабинета
-- зовёт `pub.register_failed_login(email)` для ЛЮБОГО введённого адреса, в том числе
-- несуществующего в кабинете — специально, чтобы «этот заблокирован, а этот нет» не
-- отвечало на вопрос о существовании учётки. Значит любой человек из интернета, зная
-- рабочую почту нашего сотрудника, пять раз ошибается паролем на `lk.simb-ad.com` — и
-- сотрудник на 15 минут не может войти в `timon.simbad.pro`. Повторять можно бесконечно,
-- авторизация для этого не нужна: внешний периметр закрывает вход во внутренний.
--
-- Правку делаем ЗДЕСЬ, а не в коде кабинета: тогда область — свойство самих функций
-- `pub.*`, и её нельзя забыть на новой точке вызова. Причина, по которой счётчик не
-- разделяли (одна реализация правила на оба контура), при этом сохраняется целиком:
-- таблица та же, пороги те же, функции те же — разъезжается только КЛЮЧ.
--
-- Побочный эффект, который надо знать: «перебор по обоим контурам виден в одном месте»
-- остаётся, но в `login_attempts.email` у кабинета теперь лежит `cabinet:<почта>`. Запрос
-- по этой таблице должен это учитывать.

-- Ключ области. Отдельной функцией, чтобы префикс был записан РОВНО ОДИН РАЗ: три
-- функции ниже обязаны считать один и тот же ключ, иначе блокировка ставится по одному
-- адресу, а читается по другому — и её просто не будет.
CREATE OR REPLACE FUNCTION pub.lockout_key(p_email text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'cabinet:' || lower(coalesce(p_email, ''));
$$;

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
         WHERE email = pub.lockout_key(p_email) AND locked_until > now()
         LIMIT 1), 0);
$$;

CREATE OR REPLACE FUNCTION pub.register_failed_login(p_email text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    -- Те же числа, что в ядре. Меняя их, менять в обоих местах.
    max_attempts constant int := 5;
    lock_minutes constant int := 15;
    k text := pub.lockout_key(p_email);
    cur int;
BEGIN
    -- Вставляем НОЛЬ, а не единицу: увеличивает всегда следующий UPDATE. Первая версия
    -- вставляла 1 и тут же прибавляла ещё 1 — одна неудачная попытка считалась за две,
    -- и блокировка наступала на третьей вместо пятой.
    --
    -- Регистр здесь больше не проблема: ключ уже приведён к нижнему регистру функцией
    -- области, и второй строки на «Ivan@» против «IVAN@» не заводится в принципе.
    INSERT INTO login_attempts (email, failed_count, updated_at)
    SELECT k, 0, now()
     WHERE NOT EXISTS (SELECT 1 FROM login_attempts WHERE email = k);

    UPDATE login_attempts
       SET failed_count = failed_count + 1, updated_at = now()
     WHERE email = k;

    -- Через max(), а не через RETURNING INTO: в таблице могли остаться исторические
    -- строки-двойники, и RETURNING на двух строках роняет функцию целиком — то есть
    -- отказ счётчика вместо срабатывания защиты.
    SELECT max(failed_count) INTO cur FROM login_attempts WHERE email = k;

    IF cur IS NOT NULL AND cur >= max_attempts THEN
        UPDATE login_attempts
           SET locked_until = now() + make_interval(mins => lock_minutes),
               failed_count = 0
         WHERE email = k;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION pub.clear_login_attempts(p_email text)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    DELETE FROM login_attempts WHERE email = pub.lockout_key(p_email);
$$;

GRANT EXECUTE ON FUNCTION pub.lockout_key(text)           TO cabinet;
GRANT EXECUTE ON FUNCTION pub.login_lock_minutes(text)    TO cabinet;
GRANT EXECUTE ON FUNCTION pub.register_failed_login(text) TO cabinet;
GRANT EXECUTE ON FUNCTION pub.clear_login_attempts(text)  TO cabinet;

-- Строки, накопленные общим счётчиком до этой правки, переезжают в свою область только
-- если они точно кабинетные. Отличить их можно: почта есть в `cabinet_account` и нет в
-- `users`. Всё остальное — попытки ядра, их не трогаем.
UPDATE login_attempts la
   SET email = pub.lockout_key(la.email)
 WHERE la.email NOT LIKE 'cabinet:%'
   AND EXISTS (SELECT 1 FROM cabinet_account a WHERE lower(a.email) = lower(la.email))
   AND NOT EXISTS (SELECT 1 FROM users u WHERE lower(u.email) = lower(la.email))
   AND NOT EXISTS (SELECT 1 FROM login_attempts x WHERE x.email = pub.lockout_key(la.email));
