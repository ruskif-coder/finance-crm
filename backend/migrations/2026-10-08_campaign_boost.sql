-- «Тест размещения» (08.10.2026, согласовано владельцем): временный буст объёма РК на X % на N дней
-- и предложенный трафик площадки за сутки (для оценки темпа).
-- Повторно накатываемая.

-- Один буст = одна строка. Активный — ended_at IS NULL; на РК не больше одного активного.
CREATE TABLE IF NOT EXISTS ad_campaign_boost (
    id              SERIAL PRIMARY KEY,
    campaign_id     INTEGER NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    -- на сколько процентов поднят ОСТАТОК РК (план минус факт) на момент действия буста
    pct             INTEGER NOT NULL CHECK (pct BETWEEN 1 AND 100),
    days            INTEGER NOT NULL CHECK (days >= 1),
    -- первый и последний день буста (включительно); until не позже конца флайта
    starts_on       DATE NOT NULL,
    until           DATE NOT NULL,
    -- остаток показов РК в момент нажатия: чтобы график и отчёт не пересчитывали задним числом
    rest_at_start   BIGINT,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    ended_at        TIMESTAMP,
    -- истёк / снят / РК окончена
    ended_reason    VARCHAR(32)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ad_campaign_boost_active
    ON ad_campaign_boost (campaign_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_ad_campaign_boost_campaign ON ad_campaign_boost (campaign_id);

-- Сколько показов сеть ПРЕДЛОЖИЛА площадке за сутки (bid_statistic из Statistic.getPeriod).
-- NULL — не знаем (Adfox, ручной ввод, старые строки). Ноль — предложено ноль.
ALTER TABLE ad_campaign_stat ADD COLUMN IF NOT EXISTS offered BIGINT;
