-- Добавляет редактируемую отсрочку платежа (term_days) к контрагентам.
-- Раньше отсрочка для двух контрагентов была захардкожена в reports.py (TERM_OVERRIDES_BY_INN);
-- этот скрипт переносит те же значения в БД. NULL = используется стандартная отсрочка
-- (DEFAULT_TERM_DAYS=60 в reports.py).

ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS term_days INTEGER;

UPDATE counterparties SET term_days = 90  WHERE inn = '7701906766' AND term_days IS NULL;
UPDATE counterparties SET term_days = 120 WHERE inn = '7731276913' AND term_days IS NULL;
