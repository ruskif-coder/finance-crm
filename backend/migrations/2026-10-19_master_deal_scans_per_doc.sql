-- Стадия «ждём сканы» и скан к каждому документу (владелец 19.10.2026: «1) да 2) скан к документу … касается бумажных
-- документов»). Бумага: ждём оплату → ждём сканы → архив; ЭДО идёт мимо «ждём сканы». Скан привязан к ОДНОМУ документу:
-- к ДС (annex_id) или к комплекту УПД (upd_no); на документ — один скан, замена заменяет. Повтор безопасен.
BEGIN;
ALTER TABLE master_deals DROP CONSTRAINT IF EXISTS master_deals_status_check;
ALTER TABLE master_deals ADD CONSTRAINT master_deals_status_check
    CHECK (status IN ('черновик', 'согласование', 'ждём 1С', 'выставление', 'ждём оплату', 'ждём сканы', 'архив'));

ALTER TABLE master_deal_files ADD COLUMN IF NOT EXISTS annex_id integer REFERENCES sales_annexes(id) ON DELETE CASCADE;  -- скан ДС
ALTER TABLE master_deal_files ADD COLUMN IF NOT EXISTS upd_no integer;                                                -- скан УПД № в пакете
ALTER TABLE master_deal_files ALTER COLUMN kind SET DEFAULT 'скан ДС';
CREATE UNIQUE INDEX IF NOT EXISTS ux_master_files_annex ON master_deal_files (master_deal_id, annex_id) WHERE annex_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_master_files_upd ON master_deal_files (master_deal_id, upd_no) WHERE upd_no IS NOT NULL;
COMMIT;
