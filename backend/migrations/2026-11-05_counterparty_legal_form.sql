-- Форма организации контрагента (владелец 04.11.2026, «да» на схему; окно контрагента). Без неё ИП с 12-значным ИНН не
-- регистрируется в ОРД: по ИНН не отличить ИП от физлица (`ord/payloads.legal_form`). Значения — `app/legal_form.FORMS`.
-- Начальное заполнение — по названию: ООО / ПАО / АО / ИП отдельным словом в начале или конце; ПАО раньше АО, чтобы
-- «ПАО» не стало «АО». Остальным пусто — заполнит человек в окне контрагента. Повторно накатываемая: ставит форму
-- только там, где её ещё нет.

ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS legal_form varchar(32);
COMMENT ON COLUMN counterparties.legal_form IS 'форма организации: ООО · АО · ПАО · ИП · самозанятый · физлицо · иностранная организация';

UPDATE counterparties SET legal_form = 'ПАО'
 WHERE legal_form IS NULL AND (name ~ '^\s*ПАО([\s«"]|$)' OR name ~ '[\s»"]ПАО\s*$');
UPDATE counterparties SET legal_form = 'АО'
 WHERE legal_form IS NULL AND (name ~ '^\s*АО([\s«"]|$)' OR name ~ '[\s»"]АО\s*$');
UPDATE counterparties SET legal_form = 'ООО'
 WHERE legal_form IS NULL AND (name ~ '^\s*ООО([\s«"]|$)' OR name ~ '[\s»"]ООО\s*$');
UPDATE counterparties SET legal_form = 'ИП'
 WHERE legal_form IS NULL AND (name ~ '^\s*ИП([\s«"]|$)' OR name ~ '[\s»"]ИП\s*$');
