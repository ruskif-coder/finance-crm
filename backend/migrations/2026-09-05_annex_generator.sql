-- Генератор приложений к договору (ДС): нумерация, реквизиты подписантов, шаблоны
-- формулировок. Состав согласован с владельцем 05.09.2026.
--
-- Зачем вообще: сегодня ДС ведутся вне системы — в `sales_annexes` ноль строк, а номера
-- живут текстом в `operations.ds_num` в шести форматах («1», «доп.1», «прилож. 9»).
-- По закону приложение должно существовать на момент запуска, часть клиентов просит его
-- сразу, и собирается оно руками из ворда.
--
-- Что здесь НЕТ и почему: производственного календаря. Дата приложения — последний день
-- предыдущего месяца (решение владельца 05.09.2026), это чистая арифметика, и таблица
-- праздников, которую надо обновлять раз в год, не нужна вовсе.

-- ── шаблоны формулировки услуги ──────────────────────────────────────────────
--
-- Привязка к ПЛАТЕЛЬЩИКУ, а не к рекламодателю: подписывает и платит он, у него же свои
-- требования к тексту. Бренд в формулировку приходит подстановкой — в образце
-- «Приложение № 68» это «Мезим / Mezym», а сторона договора — агентство.
CREATE TABLE IF NOT EXISTS annex_templates (
    id          SERIAL PRIMARY KEY,
    -- NULL = типовой шаблон, годный для любого плательщика.
    payer_id    INTEGER REFERENCES counterparties(id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL,
    -- Тело с подстановками {бренд} {период_с} {период_по} {сумма} {сумма_прописью}
    -- {ндс_ставка} {ндс_сумма} {ндс_сумма_прописью}. Хранится как есть: юрист правит
    -- текст, а не разметку.
    body        TEXT NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);

-- Подбор шаблона идёт от плательщика, поэтому индекс по нему.
CREATE INDEX IF NOT EXISTS ix_annex_templates_payer ON annex_templates (payer_id);

COMMENT ON TABLE annex_templates IS
  'Шаблоны формулировки услуги в приложении. payer_id NULL — типовой.';

-- ── стартовый номер на договоре ──────────────────────────────────────────────
--
-- Нумерация ведётся ВНУТРИ ДОГОВОРА (решение владельца 05.09.2026), и почти у всех
-- договоров приложения уже выданы вне системы: у «Уайт Бокс Медиа» дошли до 73.
-- Автоматически брать максимум из `operations.ds_num` нельзя — там встречается мусор
-- вроде 590425 (в поле номера записали что-то другое). Поэтому число ставит человек,
-- один раз, а экран показывает найденный максимум лишь подсказкой.
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS annex_start_no INTEGER;

COMMENT ON COLUMN contracts.annex_start_no IS
  'Последний номер приложения, выданный ВНЕ системы. Следующий = max(это, наш максимум) + 1.';

-- ── реквизиты подписанта ─────────────────────────────────────────────────────
--
-- В шапке приложения стороны представляются полностью: «в лице Генерального директора
-- Кинчикова Павла Сергеевича, действующего на основании Устава». ФИО у нас есть
-- (`director_name`), должности и основания полномочий не было ни одного.
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS signer_position VARCHAR(200);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS signer_basis    VARCHAR(300);
-- Место подписания. Живёт на контрагенте, а не константой в коде: у нашего юрлица это
-- «г. Москва», и когда юрлиц станет несколько, город поедет вместе с ними.
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS signed_place    VARCHAR(200);

COMMENT ON COLUMN counterparties.signer_basis IS
  'На основании чего действует подписант: «Устава», «Доверенности № … от …».';

-- ── само приложение ──────────────────────────────────────────────────────────
--
-- Таблица заведена раньше (зерно — договор, к сделкам привязана разнесением сумм через
-- sales_deal_annex_allocation). Здесь добавляется всё, что нужно документу.

-- Номер РАЗДЕЛЁН на два поля, и это не дублирование:
--   `no`     — целое, по нему считается следующий и держится уникальность;
--   `number` — строка, которая печатается в документе («Приложение № 68»).
-- Считать по строке нельзя (в базе шесть форматов), а печатать надо ровно то, что
-- видит клиент.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS no INTEGER;

-- Период размещения: он и в формулировке услуги, и в оговорке о ретро-действии
-- («распространяет своё действие на отношения, возникшие с 01.06.2026»).
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS period_from DATE;
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS period_to   DATE;

-- Ставка НДС НА МОМЕНТ ПОДПИСАНИЯ: в образце 22 %, до 2026 года была 20, и однажды
-- поменяется снова. Пересчитывать старое приложение по новой ставке нельзя.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS vat_rate DOUBLE PRECISION;

-- Каким шаблоном собрано. Без этой ссылки перегенерация документа через полгода дала бы
-- другой текст — шаблон к тому моменту поправят.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS template_id INTEGER REFERENCES annex_templates(id);

ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS signed_place VARCHAR(200);

-- Кто собрал и кто подтвердил номер. Подтверждение — момент, когда номер занят
-- насовсем: он ушёл клиенту.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS created_by   INTEGER REFERENCES users(id);
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS confirmed_by INTEGER REFERENCES users(id);
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP;

-- Выгруженный файл. Документ, который ушёл клиенту, обязан остаться у нас: шаблон
-- поправят, реквизиты сменятся, а подписан был именно этот.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS file_path VARCHAR(500);

-- Уникальность номера ВНУТРИ ДОГОВОРА. NULL допускается многократно — это черновики,
-- которым номер ещё не присвоен.
CREATE UNIQUE INDEX IF NOT EXISTS uq_annex_contract_no
    ON sales_annexes (contract_id, no) WHERE no IS NOT NULL;

COMMENT ON COLUMN sales_annexes.no IS
  'Порядковый номер внутри договора — по нему считается следующий.';
COMMENT ON COLUMN sales_annexes.number IS
  'Как номер печатается в документе: «Приложение № 68».';
