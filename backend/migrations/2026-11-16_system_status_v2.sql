-- «Статус системы» v2 (хендофф design_handoff_status, владелец 16.11.2026: только админ, весь пакет сразу).
-- Четыре таблицы, все повторно накатываемые. Ничего не удаляется.

-- Текущее состояние каждой проверки — пишет фоновый прогон (`python -m app.system.watch`).
-- `since` — начало ТЕКУЩЕЙ серии тона: «с 14.11 · 3 дня» на экране; первый «ok» начинает серию заново.
-- `last` — последний снимок проверки целиком: живые проверки (SSL, связь с Телеграмом) ходят наружу только в фоне,
-- а экран при открытии показывает их по этому снимку.
CREATE TABLE IF NOT EXISTS system_check_state (
    check_key        VARCHAR(64) PRIMARY KEY,
    tone             VARCHAR(8)  NOT NULL,
    since            TIMESTAMP   NOT NULL,
    last_checked_at  TIMESTAMP   NOT NULL,
    last             JSONB,
    last_failure     TEXT,          -- что было при последнем не-«ok»: показывается в раскрытой истории
    last_failure_at  TIMESTAMP
);

-- Худший тон проверки за день — история «за 14 дней» (квадраты в раскрытой строке).
CREATE TABLE IF NOT EXISTS system_check_day (
    check_key  VARCHAR(64) NOT NULL,
    day        DATE        NOT NULL,
    tone       VARCHAR(8)  NOT NULL,
    PRIMARY KEY (check_key, day)
);

-- Открытия страниц сотрудниками — «Онлайн сейчас» (окно 10 минут). Хранится сутки, чистит фоновый прогон.
CREATE TABLE IF NOT EXISTS user_page_hit (
    id       BIGSERIAL PRIMARY KEY,
    user_id  INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    path     VARCHAR(300) NOT NULL,
    at       TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_page_hit_at ON user_page_hit (at);

-- Занятость диска раз в день — прогноз «до жёлтого порога ≈ N недель» (линейно по последним 28 дням).
CREATE TABLE IF NOT EXISTS system_disk_sample (
    day          DATE   PRIMARY KEY,
    used_bytes   BIGINT NOT NULL,
    total_bytes  BIGINT NOT NULL
);

-- Ручные запуски фоновых заданий кнопкой «Запустить / Перезапустить». Пока строка не закрыта (`finished_at` пуст),
-- второй запуск того же задания база не примет — запрет параллельного запуска держит индекс, а не код.
CREATE TABLE IF NOT EXISTS system_job_run (
    id           SERIAL PRIMARY KEY,
    job_key      VARCHAR(64) NOT NULL,
    started_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    started_at   TIMESTAMP NOT NULL DEFAULT now(),
    finished_at  TIMESTAMP,
    ok           BOOLEAN,
    error        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_system_job_run_running ON system_job_run (job_key) WHERE finished_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_system_job_run_key ON system_job_run (job_key, started_at DESC);
