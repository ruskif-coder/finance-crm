-- Подписанты (владелец 28.10.2026): у юрлица их может быть несколько (например, по доверенности), один — по умолчанию; договор
-- выбирает подписанта каждой стороны из списка её юрлица. Нет выбора у договора — подписант юрлица по умолчанию.
-- Переносит нынешних подписантов из `counterparties` (director_name / signer_position / signer_basis) первым подписантом «по умолчанию».
-- Старые колонки НЕ удаляются: код их больше не читает и не пишет. Повторно накатываемая.

CREATE TABLE IF NOT EXISTS counterparty_signers (
    id              SERIAL PRIMARY KEY,
    counterparty_id INTEGER     NOT NULL REFERENCES counterparties (id) ON DELETE CASCADE,
    -- Как в документе: ФИО полностью, должность (в именительном или родительном — падеж приводит генератор), основание полномочий
    -- в родительном («Устава», «доверенности № 12 от 01.02.2026»).
    director_name   TEXT,
    signer_position TEXT,
    signer_basis    TEXT,
    -- До какого дня действует доверенность; пусто — бессрочно (устав). Истекла — ДС с этим подписантом не подтверждается.
    valid_until     DATE,
    is_default      BOOLEAN     NOT NULL DEFAULT false,
    -- В архиве — в выбор не предлагается; прежние договоры, выбравшие его, переходят на подписанта по умолчанию.
    is_archived     BOOLEAN     NOT NULL DEFAULT false,
    updated_at      TIMESTAMP   NOT NULL DEFAULT now(),
    updated_by      INTEGER     REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS ix_counterparty_signers_cp ON counterparty_signers (counterparty_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_counterparty_signer_default ON counterparty_signers (counterparty_id) WHERE is_default;
COMMENT ON TABLE counterparty_signers IS
  'Подписанты юрлица для документов (ДС); один по умолчанию. Заменили колонки counterparties.director_name/signer_position/signer_basis.';

CREATE TABLE IF NOT EXISTS contract_signers (
    contract_id INTEGER     NOT NULL REFERENCES contracts (id) ON DELETE CASCADE,
    -- Чья сторона подписывает: заказчик (контрагент договора) или исполнитель (наше юрлицо договора).
    side        VARCHAR(12) NOT NULL CHECK (side IN ('заказчик', 'исполнитель')),
    signer_id   INTEGER     NOT NULL REFERENCES counterparty_signers (id),
    updated_at  TIMESTAMP   NOT NULL DEFAULT now(),
    updated_by  INTEGER     REFERENCES users (id),
    PRIMARY KEY (contract_id, side)
);
COMMENT ON TABLE contract_signers IS
  'Кто подписывает договор с каждой стороны — выбор из подписантов юрлица этой стороны. Нет строки — подписант юрлица по умолчанию.';

-- Перенос: только юрлицам, у которых подписантов ещё нет (повторный накат ничего не дублирует).
INSERT INTO counterparty_signers (counterparty_id, director_name, signer_position, signer_basis, is_default)
SELECT c.id, nullif(btrim(c.director_name), ''), nullif(btrim(c.signer_position), ''), nullif(btrim(c.signer_basis), ''), true
  FROM counterparties c
 WHERE (coalesce(btrim(c.director_name), '') <> '' OR coalesce(btrim(c.signer_position), '') <> '' OR coalesce(btrim(c.signer_basis), '') <> '')
   AND NOT EXISTS (SELECT 1 FROM counterparty_signers s WHERE s.counterparty_id = c.id);

COMMENT ON COLUMN counterparties.director_name IS 'ЗАМОРОЖЕНО 28.10.2026: подписанты — в counterparty_signers.';
COMMENT ON COLUMN counterparties.signer_position IS 'ЗАМОРОЖЕНО 28.10.2026: подписанты — в counterparty_signers.';
COMMENT ON COLUMN counterparties.signer_basis IS 'ЗАМОРОЖЕНО 28.10.2026: подписанты — в counterparty_signers.';
