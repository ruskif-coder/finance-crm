-- Техобслуживание закрывает и кабинеты паблишеров — по выбору при объявлении (владелец 02.11.2026: «при постановке на
-- тех обслуживание надо закрывать и кабинеты паблишеров… давай выбор»).
--
-- Режим живёт в `company_settings` (app/maintenance.py), а роль `cabinet` таблиц `public` не видит. Кабинет узнаёт режим
-- из этой витрины: время начала и что закрыто («portal», «cabinet» через запятую). Текста для сотрудников и автора здесь
-- нет — площадке они ни к чему. Одна строка на всю систему, областью площадок не ограничена (как `reason_v1`).
-- Повторно накатываемая.

CREATE OR REPLACE VIEW pub.maintenance_v1 WITH (security_barrier) AS
SELECT (SELECT NULLIF(value, '') FROM company_settings WHERE key = 'maintenance_from')  AS starts_at,
       (SELECT NULLIF(value, '') FROM company_settings WHERE key = 'maintenance_scope') AS scope;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cabinet') THEN
        GRANT SELECT ON pub.maintenance_v1 TO cabinet;
    END IF;
END $$;
