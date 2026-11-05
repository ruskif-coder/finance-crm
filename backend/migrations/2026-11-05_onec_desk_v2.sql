-- «Документы для бухгалтерии» по хендоффу (владелец 05.11.2026: «делай как предложил»): черновик заявки, переписка с аккаунтом,
-- «пришла повторно» с изменениями, срок закрытия месяца и производственный календарь. Схема согласована 05.11.2026.
-- Идёт после 2026-11-05_onec_desk.sql (порядок по имени). Повторно накатываемая.

-- 1. Черновик формы бухгалтера: автосохранение, общий на заявку (кто бы из бухгалтеров ни открыл — видит то же).
--    Файлы в черновик не входят — они сразу ложатся в master_deal_files. После внесения черновик стирается.
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_draft JSONB;
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_draft_at TIMESTAMP;
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_draft_by INTEGER REFERENCES users(id);
-- Когда бухгалтер последний раз открыл заявку: метки «ответ» и «исправлено» — события аккаунта позже этого времени.
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_seen_at TIMESTAMP;
COMMENT ON COLUMN master_deal_upds.onec_draft IS 'Черновик ответа 1С, который бухгалтер набирает: номера, даты, суммы строкой как ввёл человек, разбор XML, комментарий';
COMMENT ON COLUMN master_deal_upds.onec_seen_at IS 'Бухгалтер последний раз открывал заявку — новее этого ответы и исправления аккаунта считаются непрочитанными';

-- 2. Лента: «ответ» — сообщение аккаунта бухгалтеру; снимок заявки при возврате — из него «было → стало» при повторной отправке.
ALTER TABLE onec_desk_events ADD COLUMN IF NOT EXISTS snapshot JSONB;
COMMENT ON COLUMN onec_desk_events.snapshot IS 'У возврата: реквизиты покупателя, договор, ДС, суммы и основание на момент возврата';
ALTER TABLE onec_desk_events DROP CONSTRAINT IF EXISTS onec_desk_events_kind_check;
ALTER TABLE onec_desk_events ADD CONSTRAINT onec_desk_events_kind_check
    CHECK (kind IN ('возврат', 'исправлено', 'комментарий', 'ответ', 'внесено', 'правка'));

-- 3. Закрытие месяца у бухгалтерии: срок (плашка «До закрытия октября N рабочих дней») и закрыт ли (дата в закрытом
--    периоде — предупреждение). Строки нет — срок по умолчанию 10-е число следующего месяца, 18:00 МСК, месяц открыт.
CREATE TABLE IF NOT EXISTS accounting_close (
    month      CHAR(7) PRIMARY KEY CHECK (month ~ '^\d{4}-\d{2}$'),
    close_at   TIMESTAMPTZ NOT NULL,
    closed     BOOLEAN NOT NULL DEFAULT false,
    updated_by INTEGER REFERENCES users(id),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
COMMENT ON TABLE accounting_close IS 'Закрытие учётного месяца: срок и отметка «закрыт». Меняет бухгалтер на экране «Документы для бухгалтерии»';

-- 4. Производственный календарь — только исключения из «пн–пт рабочие»: праздники в будни и рабочие выходные (переносы).
CREATE TABLE IF NOT EXISTS work_calendar (
    day        DATE PRIMARY KEY,
    is_workday BOOLEAN NOT NULL,
    note       TEXT
);
COMMENT ON TABLE work_calendar IS 'Исключения производственного календаря РФ: is_workday=false — праздник в будний день, true — рабочая суббота/воскресенье';

-- 2026: постановление Правительства РФ о переносе выходных на 2026 год (выходные 1–11 января, перенос 3 и 4 января на 9 января
-- и 31 декабря). Рабочих выходных в 2026 нет.
INSERT INTO work_calendar (day, is_workday, note) VALUES
    ('2026-01-01', false, 'Новогодние каникулы'), ('2026-01-02', false, 'Новогодние каникулы'),
    ('2026-01-05', false, 'Новогодние каникулы'), ('2026-01-06', false, 'Новогодние каникулы'),
    ('2026-01-07', false, 'Рождество'),           ('2026-01-08', false, 'Новогодние каникулы'),
    ('2026-01-09', false, 'Перенос с 3 января'),
    ('2026-02-23', false, 'День защитника Отечества'),
    ('2026-03-09', false, 'Перенос с 8 марта'),
    ('2026-05-01', false, 'Праздник Весны и Труда'),
    ('2026-05-11', false, 'Перенос с 9 мая'),
    ('2026-06-12', false, 'День России'),
    ('2026-11-04', false, 'День народного единства'),
    ('2026-12-31', false, 'Перенос с 4 января')
ON CONFLICT (day) DO NOTHING;

-- 2027: только праздники, которые выпадают на будни по закону. Переносы 2027 года — по постановлению, когда оно выйдет:
-- дописать сюда (или в таблицу) и рабочие выходные, если будут.
INSERT INTO work_calendar (day, is_workday, note) VALUES
    ('2027-01-01', false, 'Новогодние каникулы'),
    ('2027-01-04', false, 'Новогодние каникулы'), ('2027-01-05', false, 'Новогодние каникулы'),
    ('2027-01-06', false, 'Новогодние каникулы'), ('2027-01-07', false, 'Рождество'),
    ('2027-01-08', false, 'Новогодние каникулы'),
    ('2027-02-23', false, 'День защитника Отечества'),
    ('2027-03-08', false, 'Международный женский день'),
    ('2027-11-04', false, 'День народного единства')
ON CONFLICT (day) DO NOTHING;
