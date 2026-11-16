-- Проверка баннера уже при отправке на согласование (владелец 16.11.2026): до заливки в DSP проверяется пара
-- «креатив × площадка» — наш архив с имитацией разметки DSP. Та же таблица и та же проверка, что после заливки, на двух
-- этапах: строка либо про пару (отправка), либо про креатив РК (после заливки в DSP), ровно одно из двух.
ALTER TABLE dsp_banner_check ADD COLUMN IF NOT EXISTS pair_id INTEGER REFERENCES launch_prep_pair(id) ON DELETE CASCADE;
ALTER TABLE dsp_banner_check ALTER COLUMN creative_id DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_dsp_banner_check_pair ON dsp_banner_check (pair_id);
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_dsp_banner_check_one_subject') THEN
        ALTER TABLE dsp_banner_check ADD CONSTRAINT ck_dsp_banner_check_one_subject
            CHECK (num_nonnulls(creative_id, pair_id) = 1);
    END IF;
END $$;
