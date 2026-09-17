-- Заявки о сбоях: то, что заметил ЧЕЛОВЕК и не понял.
--
-- Отдельно от `debug_backlog` сознательно. Бэклог — про то, что изменили МЫ и держим под
-- наблюдением (`signal_bad`, `watch_until`); заявка — свидетельство постороннего. Разные
-- авторы, разный язык, разная цена ошибки: запись бэклога можно закрыть молча, за заявкой
-- стоит ждущий человек. Связь односторонняя: из заявки можно завести наблюдение
-- (`backlog_item_id`), обратной ссылки нет.
--
-- Схема согласована с владельцем 17.09.2026 ДО написания кода (правило проекта).
--
-- ДВА КОНТУРА АВТОРОВ. Пишут и сотрудники, и площадки, а учётки у них в разных таблицах.
-- Поэтому две необязательные ссылки и СНИМОК ИМЕНИ: учётку отключат, а заявка обязана
-- остаться читаемой — та же причина, по которой имя снимком лежит в `cabinet_log`.
--
-- ВАЖНОСТИ ОТ АВТОРА НЕТ. Человек, поймавший сбой, оценить её не может, а поле заставило
-- бы выбирать и потом спорить. Важность ставит тот, кто разбирает, — полем `severity`
-- в бэклоге, если заявка туда доросла.

CREATE TABLE IF NOT EXISTS bug_report (
    id                SERIAL PRIMARY KEY,
    -- staff | pub. Журнал общий, колонка контура обязательна: иначе половина заявок
    -- теряется из виду (решение владельца 17.09.2026).
    contour           VARCHAR(8)  NOT NULL,
    author_user_id    INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    author_account_id INTEGER     REFERENCES cabinet_account(id) ON DELETE SET NULL,
    author_name       VARCHAR(160) NOT NULL,
    publisher_id      INTEGER     REFERENCES sales_publishers(id) ON DELETE SET NULL,
    -- Обстановка снимается САМА. Заявка без адреса страницы и версии — это «у меня
    -- что-то не работает», и разбирать её дороже, чем не получать.
    page_url          VARCHAR(500),
    page_title        VARCHAR(300),
    app_version       VARCHAR(32),
    user_agent        VARCHAR(500),
    viewport          VARCHAR(32),
    comment           TEXT        NOT NULL,
    status            VARCHAR(24) NOT NULL DEFAULT 'новая',
    created_at        TIMESTAMP   NOT NULL DEFAULT now(),
    -- Когда заявку впервые открыли. Отвечает на вопрос «её вообще прочитали?» —
    -- единственный, который задаёт приславший.
    seen_at           TIMESTAMP,
    seen_by           INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    resolved_at       TIMESTAMP,
    resolved_by       INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    -- Закрытие без причины не принимается — то же правило, что в бэклоге отладки.
    resolution        TEXT,
    backlog_item_id   INTEGER     REFERENCES debug_backlog(id) ON DELETE SET NULL
);

COMMENT ON COLUMN bug_report.author_name IS
    'Снимок имени на момент подачи: учётку могут отключить, заявка остаётся читаемой.';
COMMENT ON COLUMN bug_report.seen_at IS
    'Когда заявку впервые открыли. Отвечает приславшему на вопрос «её прочитали?».';

-- Список открывается с фильтром по статусу и контуру и сортируется по дате.
CREATE INDEX IF NOT EXISTS bug_report_status_idx  ON bug_report (status, created_at DESC);
CREATE INDEX IF NOT EXISTS bug_report_contour_idx ON bug_report (contour, created_at DESC);

CREATE TABLE IF NOT EXISTS bug_report_file (
    id            SERIAL PRIMARY KEY,
    -- Каскад: скриншот без заявки не значит ничего, хранить его незачем.
    report_id     INTEGER     NOT NULL REFERENCES bug_report(id) ON DELETE CASCADE,
    rel_path      VARCHAR(300) NOT NULL,
    original_name VARCHAR(255),
    content_type  VARCHAR(100),
    size_bytes    INTEGER,
    created_at    TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS bug_report_file_report_idx ON bug_report_file (report_id);

-- Новое право. По умолчанию запрещено ВСЕМ, поэтому бэкфилл обязателен — иначе вкладку
-- не увидит и тот, кто её затевал. Наследуем состав у «Бэклога отладки»: раздача доступа
-- к этим двум вкладкам по смыслу одна.
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit)
SELECT rp.role_id, 'settings_bugs', rp.can_view, rp.can_view, rp.can_edit
  FROM role_permissions rp
 WHERE rp.section = 'settings_backlog'
   AND NOT EXISTS (SELECT 1 FROM role_permissions x
                    WHERE x.role_id = rp.role_id AND x.section = 'settings_bugs');
