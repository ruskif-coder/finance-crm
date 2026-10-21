-- Факт, введённый аккаунтом, для услуг без РК (владелец 19.10.2026: Альфарм-Таргет, Polza, OLV —
-- «форма закрытия с вводом данных»). У этих услуг РК в DSP/Adfox нет, факт берётся из отчёта партнёра и
-- вводится по каждой базовой строке медиаплана. Дальше блок «Итоговая сверка» считает как у еФарма.
-- Повторно накатываемая.
CREATE TABLE IF NOT EXISTS final_recon_fact_entries (
    id           SERIAL PRIMARY KEY,
    deal_id      INTEGER NOT NULL REFERENCES sales_deals(id) ON DELETE CASCADE,
    -- строка медиаплана, к которой относится факт; МП фиксируется на «Сборке», версия после запуска не меняется
    mp_row_id    INTEGER NOT NULL,
    -- факт в единицах модели строки (у CPM — показы)
    fact_volume  NUMERIC(16, 2) NOT NULL CHECK (fact_volume >= 0),
    -- откуда цифра: «отчёт партнёра за октябрь» и т. п.
    source_note  VARCHAR(300),
    entered_by   INTEGER REFERENCES users(id),
    entered_at   TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_fact_entry_row UNIQUE (deal_id, mp_row_id)
);
CREATE INDEX IF NOT EXISTS ix_fact_entries_deal ON final_recon_fact_entries (deal_id);
