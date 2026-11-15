-- Проверка баннера в браузере после заливки в DSP (владелец 15.11.2026): видна ли плашка «Реклама», раскрывает ли
-- она ЕРИД, ведёт ли клик по баннеру на посадочную. Строка на креатив РК — последнее состояние, не история.
-- Данные производные: проверку можно повторить в любой момент по разметке из DSP.
CREATE TABLE IF NOT EXISTS dsp_banner_check (
    id          SERIAL PRIMARY KEY,
    creative_id INTEGER NOT NULL REFERENCES ad_campaign_creative(id) ON DELETE CASCADE,
    -- отпечаток проверенной разметки из DSP: разметка поменялась — проверка устарела
    html_hash   VARCHAR(64),
    -- пусто — креатив в очереди на проверку (только что залит или перезалит)
    checked_at  TIMESTAMP,
    -- пройдена ли проверка; пусто, пока не проверяли
    ok          BOOLEAN,
    -- что не так, по размерам: {"300x600": ["плашка не видна", ...], ...}; пусто у пройденной
    problems    JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dsp_banner_check_creative ON dsp_banner_check (creative_id);
CREATE INDEX IF NOT EXISTS ix_dsp_banner_check_queue ON dsp_banner_check (creative_id) WHERE checked_at IS NULL;
