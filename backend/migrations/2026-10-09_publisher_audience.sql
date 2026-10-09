-- Заявленная аудитория площадок (владелец 09.10.2026, экран «Паблишеры → Аудитория»).
--
-- Строки, а не колонки: MAU, DAU, соцдем, аффинити живут замерами с датой и источником
-- (медиакит, Mediascope, AppMetrica, …). Новый замер не затирает старый — экран берёт
-- последний по дате, история остаётся для спора «а в прошлом медиаките было больше».
-- Поверхность (web/app) и сегмент («Ж 25–54») — необязательные грани того же замера.
--
-- «Подтверждено нами» здесь НЕ хранится: оно считается из ad_campaign_stat на лету
-- (app/sales/publisher_audience.py), хранить производное — вторая правда.
--
-- Право `dir_publishers_audience` — новое, бэкфилла ролям нет намеренно: доступ пока
-- только владельцу (admin минует проверки), остальным выдаётся галочкой в «Ролях».

CREATE TABLE IF NOT EXISTS sales_publisher_audience (
    id            SERIAL PRIMARY KEY,
    publisher_id  INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    surface_kind  VARCHAR(8),                 -- web | app | NULL = площадка целиком
    metric        VARCHAR(32) NOT NULL,       -- каталог: publisher_audience.METRICS
    segment       VARCHAR(64),                -- для долей: «Ж», «25–54», «Ж 25–54», «Москва»
    value         NUMERIC(18, 4) NOT NULL,    -- число; доли — в процентах
    source        VARCHAR(64) NOT NULL,       -- откуда цифра: медиакит, Mediascope, AppMetrica…
    measured_at   DATE NOT NULL,              -- на какую дату замер (не когда внесли)
    note          TEXT,
    created_by    INTEGER REFERENCES users(id),
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pub_audience_pub_metric
    ON sales_publisher_audience (publisher_id, metric, measured_at DESC);
