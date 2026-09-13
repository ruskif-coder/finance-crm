-- Почтовый гейт: шаблоны писем и журнал отправленного.
-- Состав согласован с владельцем 13.09.2026 («да, схема как предложил»).
--
-- ЗАЧЕМ ДВЕ ТАБЛИЦЫ, А НЕ ОДНА. Шаблон — это то, что правят; журнал — то, что случилось.
-- Держать их вместе значит либо терять историю при правке, либо плодить версии шаблона
-- ради каждого письма.
--
-- ГЛАВНОЕ ПРАВИЛО, И ОНО НЕ ТЕХНИЧЕСКОЕ. В журнал ложится ИТОГОВЫЙ ТЕКСТ письма, а не
-- ссылка на шаблон. Поправили формулировку — уже отправленное не меняется задним числом.
-- Ровно поэтому в проекте фраза запроса ссылки (`sales_url_request_phrases`) хранится у
-- получателя текстом, а не ключом: «что мы им написали» — это факт, а не вычисляемое
-- значение.

-- ── 1. Шаблоны ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mail_templates (
    id          SERIAL PRIMARY KEY,
    -- Ключ НЕИЗМЕНЯЕМ: по нему код находит шаблон. Переименование ключа = письмо
    -- перестаёт отправляться, и узнаем мы об этом от площадки, а не от системы.
    key         VARCHAR(64)  NOT NULL UNIQUE,
    title       VARCHAR(255) NOT NULL,          -- человеческое имя на экране
    subject     TEXT         NOT NULL,
    body        TEXT         NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMP,
    updated_by  INTEGER      REFERENCES users(id),
    created_at  TIMESTAMP    NOT NULL DEFAULT now()
);

COMMENT ON COLUMN mail_templates.key IS
  'Стабильный ключ, по которому код находит шаблон. Переименовывать нельзя — отправка молча перестанет находить текст.';

-- ── 2. Журнал отправленного ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mail_log (
    id           BIGSERIAL PRIMARY KEY,
    to_email     VARCHAR(320) NOT NULL,         -- предел длины адреса по RFC
    to_name      VARCHAR(255),
    -- Чей ответ ждём. Решение владельца 13.09.2026: письмо уходит ОТ СИСТЕМЫ, а ответ
    -- получателя приходит сотруднику. Адрес хранится, потому что сотрудник может уйти,
    -- а вопрос «кому отвечали» остаётся.
    reply_to     VARCHAR(320),
    subject      TEXT         NOT NULL,
    body         TEXT         NOT NULL,         -- ИТОГОВЫЙ текст, см. шапку файла
    kind         VARCHAR(32)  NOT NULL,         -- notify | url_request | …
    -- К чему относилось письмо. БЕЗ внешнего ключа намеренно: указывает в разные таблицы
    -- в зависимости от вида, как `ord_submissions.local_id` и `weborama_refs.local_id`.
    entity_type  VARCHAR(32),
    entity_id    INTEGER,
    user_id      INTEGER      REFERENCES users(id),   -- кто инициировал
    status       VARCHAR(16)  NOT NULL DEFAULT 'queued',  -- queued | sent | failed
    error        TEXT,
    attempts     INTEGER      NOT NULL DEFAULT 0,
    message_id   VARCHAR(255),                  -- Message-ID письма: по нему ищут ответ
    created_at   TIMESTAMP    NOT NULL DEFAULT now(),
    sent_at      TIMESTAMP
);

-- Читают журнал двумя способами: «что уходило по этой сделке/площадке» и «что вообще
-- не ушло». Отсюда два индекса и никаких больше.
CREATE INDEX IF NOT EXISTS ix_mail_log_entity ON mail_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_mail_log_open
    ON mail_log (created_at DESC) WHERE status <> 'sent';

COMMENT ON TABLE mail_log IS
  'Журнал писем НАРУЖУ. Внутренние уведомления сотрудникам живут в notification_deliveries: там получатель всегда наш пользователь, здесь — адрес вне системы.';

-- ── 3. Право на вкладку «Почта» ─────────────────────────────────────────────
-- Новая секция запрещена всем по умолчанию, поэтому бэкфилл обязателен — иначе право
-- есть только у админа (он проходит везде без строк) и настроить его будет некому.
--
-- Решение владельца 13.09.2026: ПРОСМОТР журнала — трафику и аккаунтам (они пишут
-- площадкам и должны видеть, дошло ли), ПРАВКА шаблонов и настроек — только админ.
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete)
SELECT r.id, 'settings_mail', 1, 0, 0, 0
  FROM roles r
 WHERE r.staff_group IN ('traffic', 'account')
   AND NOT EXISTS (SELECT 1 FROM role_permissions p
                    WHERE p.role_id = r.id AND p.section = 'settings_mail');
