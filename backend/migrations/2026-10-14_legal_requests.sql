-- Заявки аккаунта юристу по пунктам ДС после таблицы МП (спринт 3; схема согласована владельцем 14.10.2026).
-- Заявка всегда от конкретного ДС; правка юриста ложится в кастомный шаблон ДС договора (сам договор не трогаем).
-- Пока заявка открыта или в работе, её ДС нельзя подтвердить и выгрузить чистовик. Повторно накатываемая, ничего не удаляет.
CREATE TABLE IF NOT EXISTS legal_requests (
    id                SERIAL PRIMARY KEY,
    -- ДС, от которого заявка: его выпуск блокируется, пока заявка не закрыта.
    annex_id          INTEGER     NOT NULL REFERENCES sales_annexes (id),
    -- Договор ДС — для отбора в «Юр запросах»; кастомный шаблон юрист правит именно у него.
    contract_id       INTEGER     NOT NULL REFERENCES contracts (id),
    -- Пункт шаблона после таблицы МП, который просят поправить; пусто — добавить новый пункт.
    block_id          TEXT,
    -- Что просит аккаунт, своими словами.
    text              TEXT        NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'открыта'
                      CHECK (status IN ('открыта', 'в работе', 'сделана', 'отклонена')),
    -- Ответ юриста аккаунту (обязателен при отклонении).
    answer            TEXT,
    created_by        INTEGER     REFERENCES users (id),
    created_at        TIMESTAMP   NOT NULL DEFAULT now(),
    taken_by          INTEGER     REFERENCES users (id),
    taken_at          TIMESTAMP,
    closed_by         INTEGER     REFERENCES users (id),
    closed_at         TIMESTAMP,
    -- Версия кастомного шаблона договора, выпущенная юристом по заявке («сделана» без неё не закрывается).
    result_version_id INTEGER     REFERENCES annex_tpl_versions (id)
);
CREATE INDEX IF NOT EXISTS ix_legal_requests_annex ON legal_requests (annex_id);
CREATE INDEX IF NOT EXISTS ix_legal_requests_contract ON legal_requests (contract_id);
CREATE INDEX IF NOT EXISTS ix_legal_requests_open ON legal_requests (status) WHERE status IN ('открыта', 'в работе');

COMMENT ON TABLE legal_requests IS
  'Заявки аккаунта юристу по пунктам ДС после таблицы МП. Открытая заявка блокирует выпуск своего ДС.';

-- Право «Юр запросы» (контур Финансы). Ключ `legal_requests` неизменяем. Бэкфилл один раз, пока у права нет строк:
-- роль «Юрист» — просмотр и правка (взять, закрыть); остальным владелец выдаёт галочками в «Ролях».
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'legal_requests') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'legal_requests', 1, 0, 1, 0, 0, 0, 'all'
          FROM roles r
         WHERE r.label = 'Юрист';
    END IF;
END $$;

-- Юрист правит шаблон ДС договора по заявке — ему нужны создание (кастомный из базового) и правка «Шаблонов ДС» (владелец 14.10.2026).
-- Только поднимает права роли «Юрист», чужие роли не трогает; повторный прогон ничего не меняет.
INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete, can_view_operations, can_approve, deals_scope)
SELECT r.id, 'annex_templates', 1, 1, 1, 0, 0, 0, 'all' FROM roles r
 WHERE r.label = 'Юрист'
   AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = r.id AND p.section = 'annex_templates');
UPDATE role_permissions p SET can_view = 1, can_create = 1, can_edit = 1
  FROM roles r WHERE r.id = p.role_id AND r.label = 'Юрист' AND p.section = 'annex_templates';
