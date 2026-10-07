-- «Проверка креатива» (аккаунты): баннер проверяется на соответствие и нацеливается без сделки.
-- Схема согласована с владельцем 07.10.2026: ОДНА таблица, истории нет — проверка живёт 48 часов,
-- потом крон останавливает креатив нацеливания в DSP и удаляет файлы и строку.
--
-- Ничего не удаляется, повторный накат безвреден (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS creative_check (
    id            SERIAL PRIMARY KEY,
    created_by    INTEGER NOT NULL REFERENCES users(id),
    title         TEXT NOT NULL,                 -- название, чтобы различать проверки
    advertiser_url TEXT NOT NULL,                -- посадочная: домен рекламодателя (link/adomain в DSP)
    kind          VARCHAR(8) NOT NULL,           -- image | html5 (картинка хранится как html5-архив)
    original_name TEXT,
    file_path     TEXT NOT NULL,                 -- подготовленный архив, ключ внутри хранилища
    verdict       JSONB NOT NULL DEFAULT '{}',   -- замечания, что поправлено автоматически, размер, вес
    publisher_ids INTEGER[] NOT NULL DEFAULT '{}', -- площадки, показанные при создании (наши, веб)
    sandbox_token VARCHAR(64),                   -- песочница предпросмотра
    entry_path    TEXT,
    dsp_xxhash    VARCHAR(64),                   -- креатив нацеливания в DSP (демоклиент)
    dsp_state     VARCHAR(16),                   -- NULL — не заводился | live | stopped
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    expires_at    TIMESTAMP NOT NULL             -- created_at + 48 ч
);

CREATE INDEX IF NOT EXISTS ix_creative_check_user ON creative_check (created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_creative_check_expires ON creative_check (expires_at);
