-- Экран «Проверка РК» (трафики, 11.10.2026): результаты ночных проверок заведения и сбора.
-- Схема согласована владельцем 11.10.2026. Таблица новая, ничего не удаляется.
-- Хранение — 3 календарных месяца (retention.JOURNAL_MONTHS); чистит сам прогон проверок.

CREATE TABLE IF NOT EXISTS rk_check_result (
    id           BIGSERIAL PRIMARY KEY,
    run_date     DATE        NOT NULL,                 -- сутки прогона (МСК)
    campaign_id  INTEGER     NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    placement_id INTEGER     REFERENCES ad_campaign_placement(id) ON DELETE CASCADE, -- пусто = проверка про всю РК
    check_key    VARCHAR(40) NOT NULL,                 -- код проверки (app/ad/rk_check.CHECKS)
    level        VARCHAR(8)  NOT NULL,                 -- green | yellow | red | skip
    value        JSONB,                                -- числа, на которых построен вывод
    message      TEXT,                                 -- что не так простыми словами
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_rk_check_level CHECK (level IN ('green', 'yellow', 'red', 'skip'))
);
CREATE INDEX IF NOT EXISTS ix_rk_check_campaign_date ON rk_check_result (campaign_id, run_date);
CREATE INDEX IF NOT EXISTS ix_rk_check_date_level    ON rk_check_result (run_date, level);
