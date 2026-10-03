-- Уникальные показы за день (владелец 02.10.2026, импорт отчёта Adfox).
-- Отчёт Adfox даёт их по каждой кампании и дню; храним, на экраны пока не выводим.
-- У DSP и Weborama колонка пустая: NULL значит «источник этого не меряет», а не ноль.
ALTER TABLE ad_campaign_stat ADD COLUMN IF NOT EXISTS uniques integer;
