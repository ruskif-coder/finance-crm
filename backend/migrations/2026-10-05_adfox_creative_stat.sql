-- Отчёт Adfox по креативам (владелец 05.10.2026). Импорт («↑ ADFOX») знает креатив каждой
-- строки отчёта, но в `ad_campaign_stat` пишет сумму площадки за день — разбивка терялась.
-- Она нужна отчёту клиенту по РК в разрезе «креатив × площадка» и «креатив × день».
-- Факт системы по-прежнему `ad_campaign_stat` (source adfox); эта таблица — его разбивка
-- и пишется тем же импортом в той же транзакции, сумма по креативам = строке площадки.
CREATE TABLE IF NOT EXISTS adfox_creative_stat (
    id          SERIAL PRIMARY KEY,
    creative_id INTEGER NOT NULL REFERENCES ad_campaign_creative(id) ON DELETE CASCADE,
    date        DATE    NOT NULL,                 -- день показа
    shows       INTEGER NOT NULL DEFAULT 0,       -- показы креатива за день
    clicks      INTEGER NOT NULL DEFAULT 0,       -- переходы
    uniques     INTEGER,                          -- уникальные показы из отчёта, как пришли (не складываются)
    imported_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_adfox_creative_day UNIQUE (creative_id, date)
);
CREATE INDEX IF NOT EXISTS ix_adfox_creative_stat_date ON adfox_creative_stat (date);
