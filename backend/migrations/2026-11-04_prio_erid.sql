-- ЕРИД площадки приоритезации выпускает наш ОРД сам, когда площадка согласовала запрос (владелец 04.11.2026: «ерид
-- выпускается после того как площадка окнет, автоматом»; «повторить все инструкции как у креативов с адаптацией под то,
-- что у нас текст, а не баннер»). Поля — те же, что у комплекта креативов (`launch_prep_creative_set`), и значат то же:
-- маркер в `erid` (колонка уже есть), рядом — где и как он зарегистрирован. Таблица на 04.11.2026 на проде пуста.
-- Повторно накатываемая.

-- id креатива в ОРД: по нему опрашивается статус и не заводится второй креатив.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS ord_creative_id varchar(64);
-- Статус регистрации в ЕРИР: Creating..Active | RegistrationError. «Выдан» (есть erid) и «готов» — разные вещи,
-- готовность считает app/ord/readiness.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS ord_status varchar(40);
-- Текст отказа ЕРИР (erirValidationError) — что исправить аккаунту.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS ord_error text;
-- Контур ОРД рядом с идентификатором: demo | prod. Стенд — копия прода, и боевой id без контура читался бы как демо.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS ord_env varchar(8);
-- Когда статус последний раз сверен с ОРД.
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS ord_synced_at timestamp;

COMMENT ON COLUMN prio_placements.erid IS 'ЕРИД площадки: выпускает наш ОРД после согласования площадкой (с 04.11.2026), руками не вводится';
COMMENT ON COLUMN prio_placements.ord_creative_id IS 'id креатива приоритезации (форма Text) в ОРД';
COMMENT ON COLUMN prio_placements.ord_status IS 'статус регистрации креатива в ЕРИР';
COMMENT ON COLUMN prio_placements.ord_error IS 'текст отказа ЕРИР (erirValidationError)';
COMMENT ON COLUMN prio_placements.ord_env IS 'контур ОРД идентификатора: demo | prod';
COMMENT ON COLUMN prio_placements.ord_synced_at IS 'когда статус сверен с ОРД';
