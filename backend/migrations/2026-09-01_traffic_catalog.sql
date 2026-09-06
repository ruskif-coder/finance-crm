-- Каталог трафика: МС-реквизиты на существующей поверхности площадки + перепривязка блоков + право.
--
-- Заменяет ошибочную 2026-09-01_publisher_surface.sql (та плодила параллельную publisher_surface,
-- дублируя sales_publisher_surfaces из модуля паблишеров). Решение владельца 01.09.2026 —
-- переиспользовать существующую иерархию: поверхности web/app (sales_publisher_surfaces) и
-- платформы ios/android (sales_publisher_surface_platforms). МС-id живёт на web/app; когда
-- DSP реально разделит app по платформам — перенесём на платформы (таблица готова).
--
-- Идемпотентно. publisher_block наполняется импортом (scripts.import_publisher_blocks), поэтому
-- его очистка безопасна: на свежей базе пусто, локально — перезаливается из xlsx.

-- 1. МС-реквизиты на поверхность площадки (свои на каждую web/app).
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS ms_publisher_id VARCHAR;      -- id паблишера в DSP
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS default_ms_block_id VARCHAR;  -- «кукуха2»: авто-цепляется к креативу, скрыт из статистики кабинета

-- 2. Блок вешаем на существующую поверхность, а не на дубль publisher_surface.
DELETE FROM publisher_block;                                       -- строки указывали на снесённую publisher_surface; каталог перезаливается импортом
ALTER TABLE publisher_block DROP CONSTRAINT IF EXISTS publisher_block_surface_id_fkey;
ALTER TABLE publisher_block ADD COLUMN IF NOT EXISTS surface_id INTEGER;
DROP TABLE IF EXISTS publisher_surface CASCADE;                    -- ошибочный дубль (создан в этой же сессии, реальных данных нет)
ALTER TABLE publisher_block ADD CONSTRAINT publisher_block_surface_id_fkey
    FOREIGN KEY (surface_id) REFERENCES sales_publisher_surfaces(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_block_surface_msid ON publisher_block (surface_id, ms_block_id);
CREATE INDEX IF NOT EXISTS ix_publisher_block_surface ON publisher_block (surface_id);

-- 3. Право «Траффики · Каталог» (traffic_catalog). Доступ по умолчанию — мастера + админ
--    (админ обходит проверки без строк). Бэкфилл существующих мастер-ролей (is_master: 5/9/12).
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete)
SELECT id, 'traffic_catalog', 1, 1, 1, 1 FROM roles WHERE is_master = true
ON CONFLICT (role_id, section) DO NOTHING;
