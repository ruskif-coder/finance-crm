-- ДС, подписанный вне системы (владелец 02–03.11.2026). Внешний ДС — рабочий, как наш: к нему привязаны сделки, по нему
-- выставляются УПД, он уходит в 1С. Отличие одно — документ не собирается конструктором: это загруженный файл (слот «скан ДС»
-- мастер-сделки, master_deal_files) или ссылка на документ, ранее выгруженный в ЭДО. Сумму и услуги указывает аккаунт
-- (sales_annex_items); сверки с раскладкой нет — это его контроль. Комплекты УПД по-прежнему считаются из раскладки пакета.
-- Повторно накатываемая.

ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS origin varchar(12) NOT NULL DEFAULT 'система';
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS edo_link text;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sales_annexes_origin_check') THEN
        ALTER TABLE sales_annexes ADD CONSTRAINT sales_annexes_origin_check CHECK (origin IN ('система', 'загружен'));
    END IF;
END $$;

COMMENT ON COLUMN sales_annexes.origin IS 'система — документ собран конструктором; загружен — подписан вне системы (файл или ссылка ЭДО)';
COMMENT ON COLUMN sales_annexes.edo_link IS 'Ссылка на документ, ранее выгруженный в ЭДО, — документ внешнего ДС вместо файла';
