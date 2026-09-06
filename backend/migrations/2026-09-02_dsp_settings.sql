-- Настройки контура «DSP-коннектор» в ОСНОВНОЙ базе (company_settings — key/value).
-- dsp_source_key_app — ключ app-источника в DSP для Targeting.setUserSetting.
-- Открытый вопрос владельца 02.09.2026: в xlsx-каталоге app = 'x-simb', в тесте таргетинга —
-- 'xoalt_simb'. Ставим 'x-simb' как в каталоге; если верен второй — правится ЗНАЧЕНИЕМ, не кодом:
--   UPDATE company_settings SET value='xoalt_simb' WHERE key='dsp_source_key_app';
-- Идемпотентно.
INSERT INTO company_settings (key, value)
SELECT 'dsp_source_key_app', 'x-simb'
WHERE NOT EXISTS (SELECT 1 FROM company_settings WHERE key = 'dsp_source_key_app');
