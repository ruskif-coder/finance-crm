-- =====================================================================
-- Система уведомлений и алертов — схема хранения
-- Дата: 2026-08-15
-- Макет интерфейса: docs/mockup_notifications.html
--
-- Существующая таблица notifications НЕ ИЗМЕНЯЕТСЯ: она остаётся конечной
-- точкой канала «в приложении» (колокольчик). Новые таблицы стоят ДО неё —
-- решают, кому и когда слать.
--
-- Решения, согласованные с заказчиком 2026-08-15:
--   * реестр событий живёт в КОДЕ (как SECTIONS в permissions.py); в базе
--     хранится только event_key строкой, без FK — редактируемый через UI
--     список событий немедленно разъехался бы с обслуживающими функциями
--   * профиль уведомлений — самостоятельная сущность, НЕ привязан к роли:
--     роль = что можно видеть, профиль = что человека касается
--   * порядок разрешения: личная подписка → подписка профиля → дефолт реестра;
--     события с пометкой «нельзя отключить» идут мимо настроек
--   * params и recipients — JSONB: читаются всегда вместе с правилом,
--     по ним не фильтруют и не агрегируют; дочерние таблицы дали бы три
--     джойна на каждую отправку без пользы
--   * повтор алерта считается от last_sent_at («прошло не меньше N дней»),
--     а НЕ по кратности календарных дат — пропущенный прогон сканера
--     догоняется, напоминание не теряется
--   * журнал отправок хранится полгода, подрезается по расписанию
--   * один профиль на человека (не сумма профилей) — иначе невозможно
--     объяснить пользователю, почему ему что-то пришло
--   * дерево мастеров — на sales_reps, а не на users: подчинённость про
--     роль в продажах/аккаунтинге, а не про учётную запись
--
-- Только CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS —
-- ничего существующего не переписывается и не удаляется.
-- =====================================================================

-- ======================= ПРОФИЛИ И ПОДПИСКИ =======================

CREATE TABLE IF NOT EXISTS notification_profiles (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(40) NOT NULL UNIQUE,   -- 'account', 'sales', 'fin', ...
    label       VARCHAR(120) NOT NULL,         -- «Аккаунт», «Финансы»
    description VARCHAR(400),
    is_system   BOOLEAN NOT NULL DEFAULT FALSE,-- системный: нельзя удалить
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,-- подставляется новому сотруднику
    created_at  TIMESTAMP DEFAULT now(),
    created_by  INTEGER REFERENCES users(id)
);

-- Одна строка = одно событие в одной области видимости.
-- Владелец: ровно одно из profile_id / user_id (см. CHECK ниже).
CREATE TABLE IF NOT EXISTS notification_subscriptions (
    id          SERIAL PRIMARY KEY,
    profile_id  INTEGER REFERENCES notification_profiles(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    event_key   VARCHAR(60) NOT NULL,          -- ключ из реестра в коде, без FK
    is_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    ch_app      BOOLEAN NOT NULL DEFAULT TRUE,
    ch_tg       BOOLEAN NOT NULL DEFAULT FALSE,
    ch_mail     BOOLEAN NOT NULL DEFAULT FALSE,
    ch_digest   BOOLEAN NOT NULL DEFAULT FALSE,
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- пороги: {"before_days":10,"repeat_days":10}
    recipients  JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{"type":"resolver","value":"responsible"},
                                                     --  {"type":"role","value":"role_9"},
                                                     --  {"type":"user","value":12}]
    updated_at  TIMESTAMP DEFAULT now(),
    updated_by  INTEGER REFERENCES users(id),
    CONSTRAINT notif_sub_owner_ck CHECK (
        (profile_id IS NOT NULL AND user_id IS NULL) OR
        (profile_id IS NULL AND user_id IS NOT NULL)
    )
);

-- Уникальность владелец+событие. Двумя частичными индексами, а не UNIQUE(...),
-- потому что NULL в составном ключе не даёт нужной защиты от дублей.
CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_sub_profile
    ON notification_subscriptions (profile_id, event_key) WHERE profile_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_sub_user
    ON notification_subscriptions (user_id, event_key) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notif_sub_event
    ON notification_subscriptions (event_key) WHERE is_enabled;

-- ==================== ЛИЧНЫЕ НАСТРОЙКИ ДОСТАВКИ ====================

CREATE TABLE IF NOT EXISTS user_notification_channels (
    user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    tg_chat_id     VARCHAR(40),
    tg_link_code   VARCHAR(12),               -- код привязки, показывается в UI
    tg_link_expires TIMESTAMP,
    tg_verified_at TIMESTAMP,
    mail_override  VARCHAR(255),              -- если отличается от users.email
    quiet_from     SMALLINT,                  -- час начала тишины, 0..23 (NULL = без тишины)
    quiet_to       SMALLINT,
    digest_freq    VARCHAR(20) DEFAULT 'daily',-- daily | weekdays | weekly | off
    digest_hour    SMALLINT DEFAULT 9,
    digest_minute  SMALLINT DEFAULT 30,
    mute_until     DATE,                      -- «не беспокоить до» (отпуск)
    updated_at     TIMESTAMP DEFAULT now()
);

-- ===================== СОСТОЯНИЕ АЛЕРТА ПО ОБЪЕКТУ =====================
-- Гарантия «напоминание не потеряется»: повтор считается от last_sent_at,
-- а не от календарной сетки. Закрытие (оплатили / согласовали / сдвинули
-- сделку) гасит повторы, не удаляя историю.

CREATE TABLE IF NOT EXISTS notification_alert_state (
    id           SERIAL PRIMARY KEY,
    event_key    VARCHAR(60) NOT NULL,
    entity_type  VARCHAR(40) NOT NULL,        -- 'operation' | 'media_plan' | 'sales_deal' | ...
    entity_id    INTEGER NOT NULL,
    stage        VARCHAR(30),                 -- 'warning' | 'due' | 'overdue' — ступень эскалации
    first_seen_at TIMESTAMP DEFAULT now(),
    last_sent_at TIMESTAMP,
    sent_count   INTEGER NOT NULL DEFAULT 0,
    due_date     DATE,                        -- срок, от которого считается ступень
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- снимок сумм/дней на момент срабатывания
    resolved_at  TIMESTAMP,                   -- закрыт: повторы прекращены
    resolve_note VARCHAR(200)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_state
    ON notification_alert_state (event_key, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_alert_state_open
    ON notification_alert_state (event_key, last_sent_at) WHERE resolved_at IS NULL;

-- ========================= ЖУРНАЛ ОТПРАВОК =========================

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id            SERIAL PRIMARY KEY,
    event_key     VARCHAR(60) NOT NULL,
    entity_type   VARCHAR(40),
    entity_id     INTEGER,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    channel       VARCHAR(20) NOT NULL,       -- app | tg | mail | digest
    status        VARCHAR(20) NOT NULL,       -- sent | failed | suppressed | queued
    suppress_reason VARCHAR(40),              -- quiet_hours | dedup | disabled | no_channel | muted
    error         VARCHAR(400),
    title         VARCHAR(300),               -- что именно ушло (текст на момент отправки)
    notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
    created_at    TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_deliv_created ON notification_deliveries (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_deliv_user    ON notification_deliveries (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_deliv_event   ON notification_deliveries (event_key, created_at DESC);
-- очередь дайджеста: копится статусом queued, схлопывается утренней рассылкой
CREATE INDEX IF NOT EXISTS idx_notif_deliv_queued
    ON notification_deliveries (user_id) WHERE status = 'queued';

-- ========================= ПРОГОНЫ СКАНЕРА =========================
-- Без этого «алерты не приходят» не отличить от «cron не запускался».

CREATE TABLE IF NOT EXISTS notification_scan_runs (
    id           SERIAL PRIMARY KEY,
    started_at   TIMESTAMP DEFAULT now(),
    finished_at  TIMESTAMP,
    dry_run      BOOLEAN NOT NULL DEFAULT FALSE,  -- считает и пишет в лог, но не шлёт
    rules_run    INTEGER NOT NULL DEFAULT 0,
    matches      INTEGER NOT NULL DEFAULT 0,
    sent         INTEGER NOT NULL DEFAULT 0,
    suppressed   INTEGER NOT NULL DEFAULT 0,
    error        VARCHAR(600)
);

-- ==================== ПРАВКИ СУЩЕСТВУЮЩИХ ТАБЛИЦ ====================

-- Профиль уведомлений сотрудника. NULL = профиль по умолчанию (is_default).
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS notification_profile_id INTEGER REFERENCES notification_profiles(id);

-- Дерево мастеров: master_id ссылается на того же представителя.
-- Существующий флаг is_sales_head НЕ трогаем — он остаётся запасным
-- резолвером там, где master_id ещё не заполнен.
-- Обход дерева в коде — с защитой от цикла и ограничением глубины.
ALTER TABLE sales_reps
    ADD COLUMN IF NOT EXISTS master_id INTEGER REFERENCES sales_reps(id);

CREATE INDEX IF NOT EXISTS idx_sales_reps_master ON sales_reps (master_id);

-- ======================= ПРОФИЛИ ПО УМОЛЧАНИЮ =======================
-- Наполнение подписками — отдельным .py-скриптом из реестра событий,
-- чтобы дефолты не разъехались с кодом (как ACTION_LABELS в журнале).

INSERT INTO notification_profiles (key, label, description, is_system, is_default) VALUES
    ('account',     'Аккаунт',        'Медиапланы, брифы, закрывающие, движение своих сделок', TRUE, TRUE),
    ('account_master','Мастер аккаунт','Всё аккаунтское плюс эскалации по команде',            TRUE, FALSE),
    ('sales',       'Сейлз',          'Движение по воронке, план месяца, оплаты своих сделок',  TRUE, FALSE),
    ('fin',         'Финансы',        'Дебиторка, кассовый разрыв, договоры, качество данных',  TRUE, FALSE),
    ('admin',       'Администратор',  'Системные: синк, бэкапы, безопасность',                  TRUE, FALSE)
ON CONFLICT (key) DO NOTHING;
