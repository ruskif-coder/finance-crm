-- Строки услуг ДС: количество с единицей и доп. услуги (владелец 03.11.2026: «к услугам нужно единицы помимо суммы в
-- соответствии со справочником услуг», «не забудь, что могут быть доп. услуги»). Пишет их «Подписан вне системы»
-- (app/sales/annex_external.py). Единица — СНИМОК на момент подписания: смена модели закупки услуги в справочнике не должна
-- менять подписанный документ. Основная услуга — по calc_form (CPM — показы, CPC — клики, Фикс/Пакет — штуки), доп. услуга —
-- по периоду («разово» — штуки, «по итогам РК» — показы). Таблица на 03.11.2026 пуста. Повторно накатываемая.

ALTER TABLE sales_annex_items ADD COLUMN IF NOT EXISTS volume numeric(18, 2);
ALTER TABLE sales_annex_items ADD COLUMN IF NOT EXISTS unit varchar(16);
ALTER TABLE sales_annex_items ADD COLUMN IF NOT EXISTS addon_id integer REFERENCES sales_addon_services(id);
ALTER TABLE sales_annex_items ALTER COLUMN service_id DROP NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sales_annex_items_one_service') THEN
        ALTER TABLE sales_annex_items ADD CONSTRAINT sales_annex_items_one_service
            CHECK ((service_id IS NULL) <> (addon_id IS NULL));
    END IF;
END $$;

COMMENT ON COLUMN sales_annex_items.volume IS 'Количество по услуге: показы, клики или штуки — в единице unit';
COMMENT ON COLUMN sales_annex_items.unit IS 'Единица количества на момент подписания: показы | клики | штуки';
COMMENT ON COLUMN sales_annex_items.addon_id IS 'Доп. услуга (справочник доп. услуг); у строки либо service_id, либо addon_id';
