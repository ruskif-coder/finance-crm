-- 2026-10-02: какую ссылку принимает app-площадка + блоки приложений по платформам
-- (согласовано владельцем 02.10.2026). Повторно накатываемая.

-- 1. Режим ссылок app: к «веб» и «веб + диплинк» добавляется «диплинк SDK» —
--    посадочная вида deeplink+://navigate?primaryUrl=<base64 https>&primaryTrackingUrl={LINK_ESC}.
--    Значение — подсказка при заполнении, не жёсткая проверка (владелец 02.10.2026).
ALTER TABLE sales_publisher_surfaces DROP CONSTRAINT IF EXISTS ck_surface_app_links;
ALTER TABLE sales_publisher_surfaces ADD CONSTRAINT ck_surface_app_links
  CHECK (app_links IS NULL OR (kind = 'app' AND app_links IN ('web', 'both', 'sdk')));

-- 2. Платформа рекламного блока приложения: Android и iOS — разные блоки в DSP.
--    У web-блока пусто; у app — android | ios, пусто = ещё не разнесён.
ALTER TABLE publisher_block ADD COLUMN IF NOT EXISTS platform varchar(8);
DO $$ BEGIN
  ALTER TABLE publisher_block ADD CONSTRAINT ck_block_platform
    CHECK (platform IS NULL OR (surface = 'app' AND platform IN ('android', 'ios')));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
