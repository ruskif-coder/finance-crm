-- 2026-11-22_master_deal_addons_mode.sql
-- Допы в раскладке — три режима вместо «отдельным ДС да/нет» (владелец 22.11.2026):
-- separate / together / fold. addons_separate замораживается, не удаляется.
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS addons_mode varchar(8) NOT NULL DEFAULT 'separate'
    CHECK (addons_mode IN ('separate', 'together', 'fold'));
UPDATE master_deals SET addons_mode = 'together' WHERE addons_separate = false;
