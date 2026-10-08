-- bid_statistic из Statistic.getPeriod: сколько показов сеть ПРЕДЛОЖИЛА креативу за сутки (08.10.2026).
-- NULL — ответ поля не содержал. Повторно накатываемая.
ALTER TABLE dsp_stat_raw ADD COLUMN IF NOT EXISTS offered BIGINT;
