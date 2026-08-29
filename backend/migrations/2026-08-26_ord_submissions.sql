-- Обвязка ОРД, этап 2: журнал отправок и пометка контура. Согласовано 26.08.2026.
--
-- ЗАЧЕМ ЖУРНАЛ. Регистрация в ЕРИР необратима: отправленный маркер не отзывается
-- нажатием «отмена». При этом POST может уйти, а ответ — потеряться по таймауту, и
-- тогда у нас нет ни идентификатора, ни знания о том, создалась запись или нет. Повтор
-- «на всякий случай» создаёт в ЕРИР дубль. Поэтому строка журнала пишется и коммитится
-- ДО отправки, а не после ответа: незавершённая попытка (finished_at IS NULL) должна
-- блокировать повтор до тех пор, пока человек не проверит статус в кабинете.
--
-- ЗАЧЕМ ТЕЛО ЗАПРОСА. Отказ ОРД приходит как ValidationProblemDetails и указывает на
-- поле. Без сохранённого тела разобрать, что именно ушло не так, нельзя — а отправка
-- собирается из десятка мест нашей схемы.
--
-- ЗАЧЕМ КОНТУР. Демо и прод выдают РАЗНЫЕ идентификаторы. Демовский, записанный в
-- ord_contract_id, снаружи неотличим от боевого: сдача отчётности сошлётся на запись,
-- которой в ЕРИР нет. Контур хранится и у попытки, и рядом с самим идентификатором.

CREATE TABLE IF NOT EXISTS ord_submissions (
    id           SERIAL PRIMARY KEY,
    -- Что отправляли: final_contract / initial_contract / outer_contract / client /
    -- creative / invoice. Строкой, а не перечислением: набор ещё растёт по фазам,
    -- а ALTER TYPE ради каждой новой сущности — лишний ритуал.
    kind         VARCHAR(32)  NOT NULL,
    -- id НАШЕЙ записи, к которой относится отправка. Без внешнего ключа намеренно:
    -- ссылается в разные таблицы в зависимости от kind.
    local_id     INTEGER      NOT NULL,
    env          VARCHAR(8)   NOT NULL,          -- demo | prod
    request      JSONB,                          -- тело запроса, как ушло
    started_at   TIMESTAMP    NOT NULL DEFAULT now(),
    finished_at  TIMESTAMP,                      -- NULL = ответа не получили
    http_status  INTEGER,
    ord_id       VARCHAR(64),                    -- что вернул ОРД
    ord_status   VARCHAR(32),                    -- Created / Registering / Active / …
    error        TEXT,
    user_id      INTEGER REFERENCES users(id)
);

-- Главный вопрос к таблице — «нет ли незавершённой попытки по этой записи»: он задаётся
-- перед КАЖДОЙ отправкой, и отвечать на него перебором нельзя.
CREATE INDEX IF NOT EXISTS idx_ord_submissions_pending
    ON ord_submissions(kind, local_id, env) WHERE finished_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ord_submissions_local
    ON ord_submissions(kind, local_id);

-- Контур рядом с идентификатором. Аддитивно, nullable.
ALTER TABLE contracts             ADD COLUMN IF NOT EXISTS ord_env VARCHAR(8);
ALTER TABLE ord_initial_contracts ADD COLUMN IF NOT EXISTS ord_env VARCHAR(8);

-- Уже размеченные записи пришли выгрузкой из БОЕВОГО кабинета (lk.mediascout.ru) —
-- это факт, а не догадка, поэтому проставляется здесь, а не оставляется пустым:
-- пустой контур у боевого идентификатора пришлось бы трактовать, а трактовка и есть
-- то, от чего эта колонка защищает. Договоры, заведённые у нас и ещё не отправленные
-- (ord_contract_id IS NULL), контура не получают — им нечего помечать.
UPDATE contracts SET ord_env = 'prod'
 WHERE ord_contract_id IS NOT NULL AND ord_env IS NULL;
UPDATE ord_initial_contracts SET ord_env = 'prod'
 WHERE origin = 'ord' AND ord_env IS NULL;

-- Контур и отметка синка у контрагентов — то же правило, что у договоров: идентификатор
-- без контура снаружи неотличим от боевого. Добавлено при сборке фазы 1, когда
-- выяснилось, что у counterparties есть только ord_client_id и он пуст у всех 211.
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS ord_env       VARCHAR(8);
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS ord_synced_at TIMESTAMP;
