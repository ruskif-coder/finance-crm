-- Шаблоны ДС: именованные базовые шаблоны, соответствие «формат сотрудничества → базовый шаблон», версии, кастомные под договор,
-- ссылка приложения на версию (схема согласована владельцем 13–14.10.2026; docs/СХЕМА_спринт1_шаблоны_ДС.md).
-- Ничего не удаляет: старые `annex_templates` и `sales_annexes.template_id` остаются, код их больше не читает. Повторно накатываемая.

-- «Ячейка» шаблона: базовый (именованный, их может быть несколько) или кастомный под договор.
-- Текущая версия не хранится — это максимальная версия ячейки (второго источника правды нет).
CREATE TABLE IF NOT EXISTS annex_tpl_templates (
    id               SERIAL PRIMARY KEY,
    scope            VARCHAR(8)  NOT NULL CHECK (scope IN ('base', 'custom')),
    -- Только у базового: название («Основной (клиентский)»).
    title            TEXT,
    -- Только у кастомного: договор и базовый шаблон, от которого он ответвлён.
    contract_id      INTEGER     REFERENCES contracts (id),
    base_template_id INTEGER     REFERENCES annex_tpl_templates (id),
    created_at       TIMESTAMP   NOT NULL DEFAULT now(),
    created_by       INTEGER     REFERENCES users (id),
    CONSTRAINT annex_tpl_scope_shape CHECK (
        (scope = 'base'   AND title IS NOT NULL AND contract_id IS NULL     AND base_template_id IS NULL) OR
        (scope = 'custom' AND title IS NULL     AND contract_id IS NOT NULL AND base_template_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_annex_tpl_base_title
    ON annex_tpl_templates (lower(title)) WHERE scope = 'base';
CREATE UNIQUE INDEX IF NOT EXISTS uq_annex_tpl_custom_contract
    ON annex_tpl_templates (contract_id) WHERE scope = 'custom';
CREATE INDEX IF NOT EXISTS ix_annex_tpl_templates_base ON annex_tpl_templates (base_template_id);

COMMENT ON TABLE annex_tpl_templates IS
  'Ячейка шаблона ДС: базовый именованный или кастомный под договор. Версии — в annex_tpl_versions.';

-- Какой базовый шаблон обслуживает формат сотрудничества договора. Один формат — один шаблон; шаблон может обслуживать много форматов.
-- Нового варианта договора (например, агентского) достаточно завести шаблон и переключить на него форматы — миграция не нужна.
CREATE TABLE IF NOT EXISTS annex_tpl_formats (
    format      TEXT      PRIMARY KEY,
    template_id INTEGER   NOT NULL REFERENCES annex_tpl_templates (id),
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_annex_tpl_formats_template ON annex_tpl_formats (template_id);

COMMENT ON TABLE annex_tpl_formats IS
  'Формат сотрудничества договора → базовый шаблон ДС. Пустой или не заведённый формат — шаблон не определён, ДС не собирается.';

-- Версии: только добавление. Не правятся и не удаляются — на версию ссылаются выпущенные приложения.
CREATE TABLE IF NOT EXISTS annex_tpl_versions (
    id            SERIAL PRIMARY KEY,
    template_id   INTEGER   NOT NULL REFERENCES annex_tpl_templates (id),
    version       INTEGER   NOT NULL CHECK (version >= 1),
    -- Снимок блоков по порядку (заголовок, пункты, таблица МП, подписи). Проверяется annex_tpl.check при каждом сохранении.
    blocks        JSONB     NOT NULL,
    -- Изменения относительно предыдущей версии — сохраняются как есть, для показа в «Истории».
    changes       JSONB     NOT NULL DEFAULT '[]'::jsonb,
    -- Только у кастомного: версия его базового шаблона, с которой эта версия согласована
    -- (ответвление, «оставить свой», «перенять базу»). База ушла вперёд → «базовый изменился».
    base_version  INTEGER,
    -- Версия создана откатом: из какой версии взят снимок.
    restored_from INTEGER,
    author_id     INTEGER   REFERENCES users (id),
    author_name   TEXT      NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_annex_tpl_version UNIQUE (template_id, version)
);
CREATE INDEX IF NOT EXISTS ix_annex_tpl_versions_template ON annex_tpl_versions (template_id);

COMMENT ON TABLE annex_tpl_versions IS
  'Неизменяемые версии шаблона ДС. current = max(version) по template_id.';

-- Версии не правятся: триггер на UPDATE. Удаление закрыто ссылками приложений на версию и тестом (удалить версию
-- в приложении нечем); из базы вручную — осознанным действием владельца.
CREATE OR REPLACE FUNCTION annex_tpl_versions_immutable() RETURNS trigger AS $f$
BEGIN
    RAISE EXCEPTION 'annex_tpl_versions: версии шаблона не правятся — сохраните новую версию';
END;
$f$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_annex_tpl_versions_immutable ON annex_tpl_versions;
CREATE TRIGGER trg_annex_tpl_versions_immutable BEFORE UPDATE ON annex_tpl_versions
    FOR EACH ROW EXECUTE FUNCTION annex_tpl_versions_immutable();

-- Приложение помнит, по какой версии собрано, и хранит свой замороженный текст.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS template_version_id INTEGER REFERENCES annex_tpl_versions (id);
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS blocks JSONB;
CREATE INDEX IF NOT EXISTS ix_sales_annexes_template_version ON sales_annexes (template_version_id);

COMMENT ON COLUMN sales_annexes.template_version_id IS
  'Версия шаблона, по которой собрано приложение. Правка шаблона собранные приложения не меняет.';
COMMENT ON COLUMN sales_annexes.blocks IS
  'Замороженный текст приложения: правки аккаунта в зоне до таблицы МП; при подтверждении фиксируется целиком.';

-- Право «Шаблоны ДС». Ключ `annex_templates` неизменяем. Бэкфилл — один раз, пока у права нет ни одной строки:
-- просмотр получают роли с просмотром приложений; создание и правку владелец выдаёт галочками в «Ролях».
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'annex_templates') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT rp.role_id, 'annex_templates', 1, 0, 0, 0, 0, 0, 'all'
          FROM role_permissions rp
         WHERE rp.section = 'annexes' AND rp.can_view = 1;
    END IF;
END $$;

-- Рабочая группа роли «Юрист» — адресат заявок (спринт 3). Только пустую, чужое не затираем.
UPDATE roles SET staff_group = 'legal' WHERE label = 'Юрист' AND (staff_group IS NULL OR staff_group = '');
