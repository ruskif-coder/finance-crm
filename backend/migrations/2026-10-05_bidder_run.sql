-- Журнал ночных прогонов биддера (владелец 05.10.2026, страница «Трафики → Биддер»).
-- Прогон = один запуск app.ad.daily_shares: пересчёт объёмов РК и лимитов креативов в DSP.
-- Отвечает на вопросы «учитывался ли вчера факт» и «почему у площадки упал лимит».
CREATE TABLE IF NOT EXISTS bidder_run (
    id             SERIAL PRIMARY KEY,
    started_at     TIMESTAMP NOT NULL DEFAULT now(),
    finished_at    TIMESTAMP,                 -- пусто — прогон оборвался
    by_fact        BOOLEAN,                   -- учитывался ли факт (нет — раскладка по весам)
    fact_as_of     DATE,                      -- по какой день был факт
    campaigns      INTEGER,                   -- сколько РК пересчитано
    plans_changed  INTEGER,                   -- у скольких площадок поменялся план
    limits_updated INTEGER,                   -- лимитов в DSP обновлено
    limits_failed  INTEGER,                   -- лимитов в DSP не ушло
    errors         JSONB                      -- ошибки по РК и креативам
);
CREATE INDEX IF NOT EXISTS ix_bidder_run_started ON bidder_run (started_at);

-- Что поменялось у площадки в прогоне. Строка — только если план изменился.
CREATE TABLE IF NOT EXISTS bidder_run_change (
    id           SERIAL PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES bidder_run(id) ON DELETE CASCADE,
    campaign_id  INTEGER NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    placement_id INTEGER REFERENCES ad_campaign_placement(id) ON DELETE SET NULL,
    plan_before  DOUBLE PRECISION,            -- план площадки до прогона
    plan_after   DOUBLE PRECISION,            -- после
    reason       VARCHAR(16)                  -- откуда новый план: код bidder.rules.REASONS
);
CREATE INDEX IF NOT EXISTS ix_bidder_run_change_run ON bidder_run_change (run_id);
CREATE INDEX IF NOT EXISTS ix_bidder_run_change_pl ON bidder_run_change (placement_id);
