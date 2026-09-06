-- Право «Траффики · Дашборд» (traffic_dashboard) — экран открутки РК (этап 3b).
-- Решение владельца 02.09.2026: свой ключ, а не подсадка на traffic_queue/traffic_catalog —
-- дашборд нужен всем трафикам, а админка с блоками и весами только мастерам.
--
-- Бэкфилл существующих ролей (новая секция по умолчанию запрещена ВСЕМ, поэтому без бэкфилла
-- экран не увидел бы никто):
--   · рабочая группа traffic и все мастера — view + edit (edit = управление: старт/стоп/пауза);
--   · аккаунты (не мастера) — только view: смотрят открутку своих сделок, не управляют.
-- Админ проходит проверки без строк (bypass). Идемпотентно.

INSERT INTO role_permissions (role_id, section, can_view, can_edit)
SELECT id, 'traffic_dashboard', 1, 1 FROM roles
WHERE staff_group = 'traffic' OR is_master = TRUE
ON CONFLICT (role_id, section) DO NOTHING;

INSERT INTO role_permissions (role_id, section, can_view, can_edit)
SELECT id, 'traffic_dashboard', 1, 0 FROM roles
WHERE staff_group = 'account' AND is_master = FALSE
ON CONFLICT (role_id, section) DO NOTHING;
