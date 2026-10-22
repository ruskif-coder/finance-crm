-- Мост мастер-сделка → операция (владелец 20.10.2026: «при наличии счёта формируем операцию», «операция = счёт»).
-- Комплект УПД со счётом из 1С → одна операция «план поступлений». Ссылка операции на комплект — одна операция на комплект,
-- повтор моста обновляет её, а не плодит дубль. Повтор миграции безопасен.
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_invoice_date date;        -- дата счёта в 1С
ALTER TABLE operations ADD COLUMN IF NOT EXISTS master_deal_upd_id integer REFERENCES master_deal_upds(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_operations_master_deal_upd ON operations (master_deal_upd_id) WHERE master_deal_upd_id IS NOT NULL;
