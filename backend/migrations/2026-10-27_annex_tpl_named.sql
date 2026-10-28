-- Несколько именованных шаблонов ДС под один договор, основной шаблон договора, выбор шаблона в ДС и память «бренд → шаблон»
-- (владелец 27.10.2026: «хранить несколько шаблонов под один договор, сохранять их и из конструктора ДС, давать им имена; при закрытии —
-- выбор шаблона»; по умолчанию — шаблон, последним выбранный для бренда, иначе основной договора, иначе базовый его формата).
-- Ничего не удаляет из данных: снимается только ограничение «один кастомный шаблон на договор». Повторно накатываемая.

-- Имя и признак «основной» у шаблона договора. Существовавший единственный шаблон договора (до этой миграции имени у него не было)
-- получает имя и становится основным — так он и работал: собирал все ДС договора. Условие `title IS NULL` выполняется только
-- при первом накате, повторный прогон отметку «основной» не трогает.
ALTER TABLE annex_tpl_templates ADD COLUMN IF NOT EXISTS is_main BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE annex_tpl_templates DROP CONSTRAINT IF EXISTS annex_tpl_scope_shape;  -- до UPDATE: старое ограничение требовало у шаблона договора пустое имя (прод 28.10.2026)
UPDATE annex_tpl_templates SET title = 'Шаблон договора', is_main = true WHERE scope = 'custom' AND title IS NULL;

ALTER TABLE annex_tpl_templates ADD CONSTRAINT annex_tpl_scope_shape CHECK (
    (scope = 'base'   AND title IS NOT NULL AND contract_id IS NULL     AND base_template_id IS NULL     AND NOT is_main) OR
    (scope = 'custom' AND title IS NOT NULL AND contract_id IS NOT NULL AND base_template_id IS NOT NULL));

-- Было: один кастомный на договор. Стало: имена внутри договора не повторяются, основной — не больше одного.
DROP INDEX IF EXISTS uq_annex_tpl_custom_contract;
CREATE UNIQUE INDEX IF NOT EXISTS uq_annex_tpl_custom_title
    ON annex_tpl_templates (contract_id, lower(title)) WHERE scope = 'custom';
CREATE UNIQUE INDEX IF NOT EXISTS uq_annex_tpl_main
    ON annex_tpl_templates (contract_id) WHERE is_main;

COMMENT ON COLUMN annex_tpl_templates.title IS
  'Название: у базового — вариант договора («Основной (клиентский)»), у шаблона договора — имя, под которым его выбирают в ДС.';
COMMENT ON COLUMN annex_tpl_templates.is_main IS
  'Основной шаблон договора: подставляется в новый ДС, если для его брендов шаблон ещё не выбирали. Только у шаблонов договора.';

-- Какой шаблон выбран в этом ДС. Пусто — по умолчанию (память бренда → основной договора → базовый формата).
-- У подтверждённого записывается тот, по которому документ заморожен.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS tpl_template_id INTEGER REFERENCES annex_tpl_templates (id);
COMMENT ON COLUMN sales_annexes.tpl_template_id IS
  'Шаблон ДС, выбранный для приложения; пусто — шаблон по умолчанию. Не путать со старым template_id (шаблон по плательщику, не читается).';

-- Память «договор + бренд → шаблон»: обновляется при подтверждении ДС для каждого его бренда.
CREATE TABLE IF NOT EXISTS annex_tpl_brand_memory (
    contract_id INTEGER   NOT NULL REFERENCES contracts (id),
    brand_id    INTEGER   NOT NULL REFERENCES sales_brands (id),
    template_id INTEGER   NOT NULL REFERENCES annex_tpl_templates (id),
    updated_at  TIMESTAMP NOT NULL DEFAULT now(),
    updated_by  INTEGER   REFERENCES users (id),
    PRIMARY KEY (contract_id, brand_id)
);
COMMENT ON TABLE annex_tpl_brand_memory IS
  'Последний шаблон ДС, по которому подтверждено приложение с этим брендом в этом договоре: подставляется в следующий ДС бренда.';
