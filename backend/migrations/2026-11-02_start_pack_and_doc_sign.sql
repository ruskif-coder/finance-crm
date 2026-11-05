-- ДС на старте через конструктор закрытия и подпись у каждого документа пакета (владелец 02.11.2026, состав согласован).
--
-- 1. Пакет, заведённый на старте (кнопка «Создать» в карточке сделки со «Сборки»): одна сделка, к нему никого не присоединяют,
--    раскладка по МП, ДС — первичный. После «Подтвердить ДС» пакет ждёт закрытия; «Отправить в ДО» возвращает его в черновик.
-- 2. Подпись — у КАЖДОГО документа (ДС и УПД): клиент может отказать в подписи одного документа пакета после всех
--    согласований. Пока Диадок не подключён — отметки руками, потом из ЭДО. Пакетные sent_at / signed_by_us_at / docs_closed_at
--    остаются в базе историей, код их больше не читает.
-- 3. Заполнение у существующих документов — по тем же признакам, что код читал до сих пор.
-- Повтор безопасен: IF NOT EXISTS, заполнение только пустых.
BEGIN;

-- 1. Пакет на старте и его статус «ждём закрытия»
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS issued_at_start boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN master_deals.issued_at_start IS
    'Заведён на старте ради первичного ДС: одна сделка, без объединения; закрывается этим же пакетом';
ALTER TABLE master_deals DROP CONSTRAINT IF EXISTS master_deals_status_check;
ALTER TABLE master_deals ADD CONSTRAINT master_deals_status_check
    CHECK (status IN ('черновик', 'согласование', 'ждём закрытия', 'ждём 1С', 'выставление', 'ждём оплату', 'ждём сканы', 'архив'));

-- 2. Состояние подписи у документа
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS sign_state varchar(20);
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS sign_channel varchar(10);
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS sign_state varchar(20);
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS sign_channel varchar(10);
COMMENT ON COLUMN sales_annexes.sign_state IS
    'Где документ у клиента: пусто — черновик; выпущен → согласован → (бумага: подписан у нас) → выставлен → подписан | отклонён';
COMMENT ON COLUMN master_deal_upds.sign_state IS
    'Где УПД у клиента: пусто — пришёл из 1С; (бумага: подписан у нас) → выставлен → подписан | отклонён';
COMMENT ON COLUMN sales_annexes.sign_channel IS 'Как ушёл клиенту: ЭДО или бумага — по признаку договора на момент выставления';
COMMENT ON COLUMN master_deal_upds.sign_channel IS 'Как ушёл клиенту: ЭДО или бумага — по признаку договора на момент выставления';

ALTER TABLE sales_annexes DROP CONSTRAINT IF EXISTS sales_annexes_sign_state_check;
ALTER TABLE sales_annexes ADD CONSTRAINT sales_annexes_sign_state_check
    CHECK (sign_state IS NULL OR sign_state IN ('выпущен', 'согласован', 'подписан у нас', 'выставлен', 'подписан', 'отклонён'));
ALTER TABLE master_deal_upds DROP CONSTRAINT IF EXISTS master_deal_upds_sign_state_check;
ALTER TABLE master_deal_upds ADD CONSTRAINT master_deal_upds_sign_state_check
    CHECK (sign_state IS NULL OR sign_state IN ('подписан у нас', 'выставлен', 'подписан', 'отклонён'));
ALTER TABLE sales_annexes DROP CONSTRAINT IF EXISTS sales_annexes_sign_channel_check;
ALTER TABLE sales_annexes ADD CONSTRAINT sales_annexes_sign_channel_check
    CHECK (sign_channel IS NULL OR sign_channel IN ('ЭДО', 'бумага'));
ALTER TABLE master_deal_upds DROP CONSTRAINT IF EXISTS master_deal_upds_sign_channel_check;
ALTER TABLE master_deal_upds ADD CONSTRAINT master_deal_upds_sign_channel_check
    CHECK (sign_channel IS NULL OR sign_channel IN ('ЭДО', 'бумага'));

-- История: отказ и повторная отправка — несколько кругов по одному документу, колонки документа держат только последний.
CREATE TABLE IF NOT EXISTS doc_sign_events (
    id          serial PRIMARY KEY,
    annex_id    integer REFERENCES sales_annexes(id) ON DELETE CASCADE,
    upd_id      integer REFERENCES master_deal_upds(id) ON DELETE CASCADE,
    state       varchar(20) NOT NULL,
    channel     varchar(10),
    source      varchar(10) NOT NULL DEFAULT 'вручную',     -- вручную | ЭДО | перенос (заполнение этой миграцией)
    reason      text,                                       -- причина отказа клиента
    file_id     integer REFERENCES master_deal_files(id) ON DELETE SET NULL,   -- скан подписанного, если он был основанием
    by_user     integer REFERENCES users(id),
    at          timestamp NOT NULL DEFAULT now(),
    CONSTRAINT doc_sign_events_one_doc CHECK ((annex_id IS NULL) <> (upd_id IS NULL)),
    CONSTRAINT doc_sign_events_source_check CHECK (source IN ('вручную', 'ЭДО', 'перенос'))
);
CREATE INDEX IF NOT EXISTS doc_sign_events_annex_idx ON doc_sign_events (annex_id) WHERE annex_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS doc_sign_events_upd_idx ON doc_sign_events (upd_id) WHERE upd_id IS NOT NULL;

-- 3. Заполнение. Порядок важен: сначала «подписан» по скану, потом «выставлен» по отправке пакета, потом «выпущен» — остальным
--    подтверждённым. Каждый шаг трогает только пустые.
-- ДС пакета со сканом — подписан (бумага)
UPDATE sales_annexes a SET sign_state = 'подписан', sign_channel = 'бумага'
  FROM master_deal_files f
 WHERE f.annex_id = a.id AND a.no IS NOT NULL AND a.sign_state IS NULL;
-- УПД со сканом — подписан (бумага)
UPDATE master_deal_upds u SET sign_state = 'подписан', sign_channel = 'бумага'
  FROM master_deal_files f
 WHERE f.master_deal_id = u.master_deal_id AND f.upd_no = u.upd_no AND u.sign_state IS NULL
   AND f.kind = 'скан УПД';   -- с 05.11.2026 рядом лежат PDF из 1С с тем же upd_no — они не подпись
-- Документы пакета закрыты (`docs_closed_at`): у ЭДО до 02.11.2026 их закрывала сама отправка, у бумаги — сканы. Это
-- прочтение «подписан» сохраняем: иначе отправленные ЭДО-пакеты не дошли бы до архива без ручной отметки каждого документа,
-- а архивные потеряли бы дату «документы закрыты» (ревью 02.11.2026).
UPDATE sales_annexes a SET sign_state = 'подписан',
       sign_channel = CASE WHEN m.signed_by_us_at IS NOT NULL THEN 'бумага' ELSE 'ЭДО' END
  FROM master_deals m
 WHERE a.master_deal_id = m.id AND m.docs_closed_at IS NOT NULL AND a.no IS NOT NULL AND a.sign_state IS NULL;
UPDATE master_deal_upds u SET sign_state = 'подписан',
       sign_channel = CASE WHEN m.signed_by_us_at IS NOT NULL THEN 'бумага' ELSE 'ЭДО' END
  FROM master_deals m
 WHERE u.master_deal_id = m.id AND m.docs_closed_at IS NOT NULL AND u.sign_state IS NULL;
-- Файл ДС у сделки считался подписью (annex_signed до 02.11.2026) — у ДС вне пакетов И у первичных, уже привязанных к пакету
-- закрытием по подписанному. Без второго условия подписанный первичный стал бы «выпущен» и пересобрался (ревью 02.11.2026).
UPDATE sales_annexes a SET sign_state = 'подписан'
 WHERE (a.master_deal_id IS NULL OR a.issue_kind = 'primary') AND a.no IS NOT NULL AND a.sign_state IS NULL
   AND EXISTS (SELECT 1 FROM sales_deal_annex_allocation al JOIN sales_deal_files f ON f.deal_id = al.deal_id AND f.kind = 'ds'
                WHERE al.annex_id = a.id);
-- Пакет отправлен — его документы выставлены тем каналом, каким ушёл пакет (подпись у нас — бумага, иначе ЭДО)
UPDATE sales_annexes a SET sign_state = 'выставлен',
       sign_channel = CASE WHEN m.signed_by_us_at IS NOT NULL THEN 'бумага' ELSE 'ЭДО' END
  FROM master_deals m
 WHERE a.master_deal_id = m.id AND m.sent_at IS NOT NULL AND a.no IS NOT NULL AND a.sign_state IS NULL;
UPDATE master_deal_upds u SET sign_state = 'выставлен',
       sign_channel = CASE WHEN m.signed_by_us_at IS NOT NULL THEN 'бумага' ELSE 'ЭДО' END
  FROM master_deals m
 WHERE u.master_deal_id = m.id AND m.sent_at IS NOT NULL AND u.sign_state IS NULL;
-- Подписано у нас, но ещё не отправлено (бумага)
UPDATE sales_annexes a SET sign_state = 'подписан у нас', sign_channel = 'бумага'
  FROM master_deals m
 WHERE a.master_deal_id = m.id AND m.signed_by_us_at IS NOT NULL AND a.no IS NOT NULL AND a.sign_state IS NULL;
UPDATE master_deal_upds u SET sign_state = 'подписан у нас', sign_channel = 'бумага'
  FROM master_deals m
 WHERE u.master_deal_id = m.id AND m.signed_by_us_at IS NOT NULL AND u.sign_state IS NULL;
-- Остальные подтверждённые ДС — выпущены
UPDATE sales_annexes SET sign_state = 'выпущен' WHERE no IS NOT NULL AND sign_state IS NULL;

-- След переноса в истории — один раз на документ
INSERT INTO doc_sign_events (annex_id, state, channel, source)
SELECT a.id, a.sign_state, a.sign_channel, 'перенос' FROM sales_annexes a
 WHERE a.sign_state IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doc_sign_events e WHERE e.annex_id = a.id);
INSERT INTO doc_sign_events (upd_id, state, channel, source)
SELECT u.id, u.sign_state, u.sign_channel, 'перенос' FROM master_deal_upds u
 WHERE u.sign_state IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doc_sign_events e WHERE e.upd_id = u.id);

-- 4. Право. «Создать» ДС в карточке сделки заводит стартовую мастер-сделку и требует «Мастер-сделки: правка», а раньше хватало
--    «ДС: создание». Владелец 02.11.2026: у кого есть «ДС: создание» — получает и «Мастер-сделки: просмотр + правка», иначе роль
--    теряет кнопку. Только добавляет, ничего не снимает.
INSERT INTO role_permissions (role_id, section, can_view, can_edit)
SELECT p.role_id, 'master_deals', 1, 1 FROM role_permissions p
 WHERE p.section = 'annexes' AND p.can_create = 1
ON CONFLICT (role_id, section) DO UPDATE SET can_view = 1, can_edit = 1;

COMMIT;
