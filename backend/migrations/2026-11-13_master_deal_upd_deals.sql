-- Комплект закрывающих (счёт + УПД) — из каких сделок и на какую сумму он собран (владелец 13.11.2026).
-- Раскладка мастер-сделки считает это при сборке, но до сих пор не записывала: карточка сделки не могла показать
-- «свои» комплекты, когда пакет собран из нескольких сделок и комплекты с ними не совпадают.
-- Формат: [{"deal_id": 123, "code": "QGNY4M", "net": 1000.00, "gross": 1220.00}, …] — доля сделки до НДС и с НДС.
-- Заполняется при создании ДС пакета (`to_annex.write_kits`); у существующих — разовым скриптом
-- `scripts.backfill_master_upd_deals_2026_11_13`. Пусто — разбивка неизвестна (старый пакет до досчёта).
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS deals JSONB;

COMMENT ON COLUMN master_deal_upds.deals IS
  'Сделки комплекта и их доля: [{deal_id, code, net, gross}]. Источник — раскладка мастер-сделки при создании ДС.';

CREATE INDEX IF NOT EXISTS ix_master_deal_upds_deals ON master_deal_upds USING GIN (deals jsonb_path_ops);
