-- Лог РК (владелец 05.11.2026): журнал заметок по рекламной кампании на дашборде трафика.
-- Каждая заметка — отдельная запись; править нельзя (триггер ниже), ошибку исправляют новой записью.
-- Удаляется лог только вместе с РК (каскад от сделки): иначе удаление сделки упиралось бы в журнал.
-- Площадке лог не уходит никогда — в кабинет, письма и бот не подключается.

CREATE TABLE IF NOT EXISTS ad_campaign_note (
    id          SERIAL PRIMARY KEY,
    campaign_id INTEGER     NOT NULL REFERENCES ad_campaign(id) ON DELETE CASCADE,
    author_id   INTEGER     REFERENCES users(id),        -- кто написал; учётку могут удалить — имя ниже снимком
    author_name TEXT        NOT NULL,                     -- имя автора на момент записи
    kind        VARCHAR(16) NOT NULL DEFAULT 'note'
                CHECK (kind IN ('note', 'agreement', 'problem')),   -- заметка · договорённость · проблема
    text        TEXT        NOT NULL CHECK (length(btrim(text)) BETWEEN 1 AND 2000),
    created_at  TIMESTAMP   NOT NULL DEFAULT now()        -- время ставит сервер (UTC, показ — МСК)
);

CREATE INDEX IF NOT EXISTS ad_campaign_note_campaign_idx ON ad_campaign_note (campaign_id, created_at DESC, id DESC);

-- Журнал: запись не правится. Удаление — только каскадом вместе с РК.
CREATE OR REPLACE FUNCTION ad_campaign_note_no_update() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'лог РК не правится: исправление — новой записью';
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ad_campaign_note_no_update ON ad_campaign_note;
CREATE TRIGGER ad_campaign_note_no_update BEFORE UPDATE ON ad_campaign_note
  FOR EACH ROW EXECUTE FUNCTION ad_campaign_note_no_update();
