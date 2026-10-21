-- Статусы мастер-сделки (владелец 19.10.2026): черновик → согласование → ждём 1С → выставление → ждём оплату → архив.
-- Прежние значения переводятся один к одному. Ограничение значений меняется вместе с ними (снимается старое, ставится новое —
-- данные не теряются). Повтор безопасен: новых значений UPDATE не касается, ограничение пересоздаётся тем же.
-- «ждём сканы» — и здесь тоже (ревью 21.10.2026): по имени эта миграция идёт ПОСЛЕ 2026-10-19_master_deal_scans_per_doc и без
-- него сняла бы этот статус — на чистой базе бумажный пакет падал бы на ограничении при переходе в «ждём сканы».
BEGIN;
ALTER TABLE master_deals DROP CONSTRAINT IF EXISTS master_deals_status_check;
UPDATE master_deals SET status = CASE status
    WHEN 'сборка'      THEN 'черновик'
    WHEN 'ДС'          THEN 'согласование'
    WHEN 'в 1С'        THEN 'ждём 1С'
    WHEN 'закрывающие' THEN 'выставление'
    WHEN 'закрыт'      THEN 'архив'
    ELSE status END
 WHERE status IN ('сборка', 'ДС', 'в 1С', 'закрывающие', 'закрыт');
ALTER TABLE master_deals ADD CONSTRAINT master_deals_status_check
    CHECK (status IN ('черновик', 'согласование', 'ждём 1С', 'выставление', 'ждём оплату', 'ждём сканы', 'архив'));
ALTER TABLE master_deals ALTER COLUMN status SET DEFAULT 'черновик';
COMMIT;
