-- Отзыв входов кабинета паблишера (внешний аудит 2.6.76, п. 1.6; владелец 22.10.2026: «1.6 делай»).
-- Счётчик входит в отпечаток токена (`pwv`, как `users.token_epoch` ядра с 07.10.2026): растёт — выданные токены учётки
-- больше не принимаются. Растёт при «Выйти» (функция ниже) и при отключении/включении учётки (ядро, routers/cabinets.py).
-- 0 по умолчанию — уже выданные входы не слетают. Повтор безопасен.
ALTER TABLE cabinet_account ADD COLUMN IF NOT EXISTS token_epoch integer NOT NULL DEFAULT 0;

-- Представление кабинета — прежние колонки и счётчик в конце (CREATE OR REPLACE VIEW дописывает только в конец).
CREATE OR REPLACE VIEW pub.account_v1 WITH (security_barrier = true) AS
SELECT id, email, name, hashed_password, is_active, can_approve, consent_accepted_at, token_epoch
  FROM cabinet_account a;

-- «Выйти» — запись от имени ядра: у роли кабинета нет права писать в таблицу, только вызвать эту функцию.
CREATE OR REPLACE FUNCTION pub.logout(p_account_id integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $$
DECLARE
    v integer;
BEGIN
    UPDATE cabinet_account SET token_epoch = token_epoch + 1 WHERE id = p_account_id RETURNING token_epoch INTO v;
    RETURN v;
END
$$;
REVOKE ALL ON FUNCTION pub.logout(integer) FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cabinet') THEN
        GRANT EXECUTE ON FUNCTION pub.logout(integer) TO cabinet;
    END IF;
END $$;
