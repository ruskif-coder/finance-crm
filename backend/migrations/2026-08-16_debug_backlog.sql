-- Бэклог отладки: что держим под наблюдением после больших изменений.
--
-- Зачем отдельно от журнала действий: журнал отвечает на вопрос «что было сделано»,
-- а здесь — «что может выстрелить и по какому признаку это опознать». Через две недели
-- после правки никто не помнит, что именно надо было заметить, поэтому признак поломки
-- хранится явным полем, а не в голове автора.
--
-- Накатывается так же, как остальные миграции проекта:
--   docker exec -i finance_db psql -U finance_user -d finance < backend/migrations/2026-08-16_debug_backlog.sql

CREATE TABLE IF NOT EXISTS debug_backlog (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(300) NOT NULL,
    area         VARCHAR(80),                       -- раздел системы: навигация, уведомления, финансы…
    context      TEXT,                              -- что изменилось и почему запись здесь
    signal_ok    TEXT,                              -- как выглядит «всё в порядке»
    signal_bad   TEXT,                              -- как опознать поломку; главное поле записи
    severity     VARCHAR(20)  NOT NULL DEFAULT 'средняя',   -- низкая | средняя | высокая
    status       VARCHAR(24)  NOT NULL DEFAULT 'наблюдаем', -- наблюдаем | подтвердилось | закрыто | не воспроизвелось
    watch_until  DATE,                              -- до какой даты держим; иначе список растёт вечно
    source_link  VARCHAR(500),                      -- ссылка на спеку, задачу или запись журнала
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by   INTEGER REFERENCES users(id),
    resolved_at  TIMESTAMP,
    resolved_by  INTEGER REFERENCES users(id),
    resolution   TEXT,                              -- чем кончилось
    -- Отметка последнего уведомления о просрочке: без неё сканер напоминал бы каждый прогон.
    overdue_notified_at TIMESTAMP
);

-- Наблюдения по записи. Отдельной таблицей, потому что ценность записи — в череде
-- проверок («21-го чисто», «23-го всплыло»); в одном поле эта история затирается.
CREATE TABLE IF NOT EXISTS debug_backlog_notes (
    id         SERIAL PRIMARY KEY,
    item_id    INTEGER NOT NULL REFERENCES debug_backlog(id) ON DELETE CASCADE,
    author_id  INTEGER REFERENCES users(id),
    text       TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_debug_backlog_status ON debug_backlog (status);
CREATE INDEX IF NOT EXISTS ix_debug_backlog_watch_until ON debug_backlog (watch_until);
CREATE INDEX IF NOT EXISTS ix_debug_backlog_notes_item ON debug_backlog_notes (item_id);
