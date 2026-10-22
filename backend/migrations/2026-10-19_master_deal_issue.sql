-- Выставление пакета закрытия: вилка ЭДО / бумага (владелец 19.10.2026, состав утверждён).
-- ЭДО (до интеграции): отметка «отправлено» закрывает документы. Бумага: подписано у нас → отправлено (трек) → сканы
-- подписанных закрывают документы. Архив пакета — только при закрытых документах. Повтор безопасен.
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS signed_by_us_at timestamp;          -- бумага: подписано у нас
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS signed_by_us_by integer REFERENCES users(id);
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS sent_at timestamp;                  -- отправлено клиенту (ЭДО или бумага)
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS sent_by integer REFERENCES users(id);
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS track_no varchar(64);               -- бумага: трек-номер, по желанию
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS docs_closed_at timestamp;           -- документы закрыты: ЭДО — отправкой, бумага — сканами
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS docs_closed_by integer REFERENCES users(id);

-- Сканы подписанных документов пакета (и другие файлы пакета — по виду). Файл — в /app/uploads/master_files.
CREATE TABLE IF NOT EXISTS master_deal_files (
    id             serial PRIMARY KEY,
    master_deal_id integer NOT NULL REFERENCES master_deals(id) ON DELETE CASCADE,
    kind           varchar(32) NOT NULL DEFAULT 'скан подписанных',
    filename       varchar(300) NOT NULL,
    path           varchar(500) NOT NULL,                 -- относительно /app/uploads
    size           integer,
    content_type   varchar(120),
    uploaded_by    integer REFERENCES users(id),
    uploaded_at    timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_master_deal_files_master ON master_deal_files (master_deal_id);

-- Через сколько дней после отправки бумажного пакета без сканов «прикрепить сканы» горит красным (владелец 19.10.2026: по умолчанию 30).
INSERT INTO company_settings (key, value) VALUES ('master_scans_due_days', '30') ON CONFLICT (key) DO NOTHING;
