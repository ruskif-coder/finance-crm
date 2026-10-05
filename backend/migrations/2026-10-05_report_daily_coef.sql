-- Коэффициенты отчёта клиенту «SIMB ID» (владелец 05.10.2026). Для каждой пары «площадка ×
-- креатив» (строка ad_campaign_creative) на каждый день один раз выбирается частота и CTR:
-- базовое значение из настроек ± случайная поправка в пределах заданного %. Значение
-- фиксируется и больше не меняется — повторные выгрузки отчёта дают те же цифры, даже если
-- настройки потом поправили. Производные (уники = показы ÷ частота, клики-модель = показы ×
-- CTR) не хранятся: считаются от РЕАЛЬНЫХ показов, на которые поправок нет.
CREATE TABLE IF NOT EXISTS report_daily_coef (
    id          SERIAL PRIMARY KEY,
    creative_id INTEGER NOT NULL REFERENCES ad_campaign_creative(id) ON DELETE CASCADE,
    date        DATE    NOT NULL,                  -- день показа
    freq        NUMERIC(6, 2) NOT NULL,            -- частота дня (показов на человека)
    ctr_pct     NUMERIC(8, 4) NOT NULL,            -- CTR дня, %
    computed_at TIMESTAMP NOT NULL DEFAULT now(),  -- когда зафиксировано
    CONSTRAINT uq_report_coef_day UNIQUE (creative_id, date)
);
CREATE INDEX IF NOT EXISTS ix_report_daily_coef_date ON report_daily_coef (date);
