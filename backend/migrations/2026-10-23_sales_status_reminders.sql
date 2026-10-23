-- «Статусы продаж»: будильник на строку рекламодателя или бренда и «факт» у сделок в работе.
-- Состав согласован с владельцем 23.10.2026. Повторный накат безопасен.

-- Будильник: человек ставит себе напоминание на дату; в 09:00 МСК этого дня сканер уведомлений шлёт его в Telegram и на
-- почту (событие sales_status_reminder) и отмечает sent_at. Один будильник на строку у каждого; новая дата снимает отметку.
CREATE TABLE IF NOT EXISTS sales_status_reminders (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,          -- чей будильник (ставят себе)
    advertiser_id INTEGER REFERENCES sales_advertisers(id) ON DELETE CASCADE,       -- строка рекламодателя или его бренда
    brand_id      INTEGER REFERENCES sales_brands(id) ON DELETE CASCADE,            -- пусто — строка рекламодателя
    client_name   VARCHAR(300),                                                     -- клиент из Excel вне справочника
    remind_on     DATE NOT NULL,                                                    -- в какой день напомнить
    note          TEXT,                                                             -- о чём
    sent_at       TIMESTAMP,                                                        -- когда ушло; пусто — ещё ждёт
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    updated_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_ssr_owner CHECK ((advertiser_id IS NOT NULL) <> (client_name IS NOT NULL)),
    CONSTRAINT ck_ssr_brand CHECK (brand_id IS NULL OR advertiser_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ssr_user_row
    ON sales_status_reminders (user_id, coalesce(advertiser_id, 0), coalesce(brand_id, 0), lower(coalesce(client_name, '')));
CREATE INDEX IF NOT EXISTS ix_ssr_due ON sales_status_reminders (remind_on) WHERE sent_at IS NULL;

-- Сделка в работе (после Брони) — «факт» в базе, а не только на экране: светофор дашборда и колонка «Статусов» совпадают.
UPDATE sales_deals d SET probability_color = 'green'
  FROM sales_stages s
 WHERE s.id = d.our_stage_id
   AND s.stage_key IN ('launch_prep', 'launch', 'closing', 'closing_fact', 'archive')
   AND NOT coalesce(s.is_lost, false)
   AND d.probability_color IS DISTINCT FROM 'green';
