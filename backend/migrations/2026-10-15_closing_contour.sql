-- Контур закрытия еФарм (владелец 15.10.2026, схема docs/СХЕМА_контур_закрытия_еФарм.md).
-- Повторно накатываемая: только IF NOT EXISTS, ничего не удаляется.

-- 1. Бонусный трафик — особенность РК: одно из трёх — % от плана, количество показов или сумма без НДС.
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS bonus_traffic_mode  varchar(8);
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS bonus_traffic_value numeric(14,2);
DO $$ BEGIN
  ALTER TABLE sales_deals ADD CONSTRAINT sales_deals_bonus_traffic_check CHECK (
    (bonus_traffic_mode IS NULL AND bonus_traffic_value IS NULL)
    OR (bonus_traffic_mode IN ('pct', 'qty', 'rub') AND bonus_traffic_value > 0));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 2. Итоговая сверка сделки: выбранный пин суммы ДС, ручная сумма и цифры, замороженные на «Отправить в ДО».
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS ds_mode       varchar(8);
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS ds_manual_net numeric(14,2);
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS plan_shows    bigint;
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS fact_shows    bigint;
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS bonus_shows   bigint;
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS base_net      numeric(14,2);
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS sent_at       timestamp;
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS sent_by       integer REFERENCES users(id);
DO $$ BEGIN
  ALTER TABLE final_recon_deals ADD CONSTRAINT final_recon_deals_ds_mode_check CHECK (
    ds_mode IS NULL OR ds_mode IN ('fact', 'plan', 'manual'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE final_recon_deals ADD CONSTRAINT final_recon_deals_manual_check CHECK (
    ds_mode IS DISTINCT FROM 'manual' OR ds_manual_net IS NOT NULL);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 3. Мастер-сделка: юридическая обёртка под ДС; заводится всегда, даже на одну сделку. Ключ — доходный договор и месяц.
CREATE SEQUENCE IF NOT EXISTS master_deal_no_seq;
CREATE TABLE IF NOT EXISTS master_deals (
    id                     serial PRIMARY KEY,
    code                   varchar(20) NOT NULL UNIQUE,      -- сквозной номер M-0001 (для людей и 1С)
    contract_id            integer NOT NULL REFERENCES contracts(id),
    period                 char(7) NOT NULL,                 -- финансовый месяц YYYY-MM
    payer_counterparty_id  integer REFERENCES counterparties(id),
    status                 varchar(20) NOT NULL DEFAULT 'сборка'
                           CHECK (status IN ('сборка', 'ДС', 'закрывающие', 'в 1С', 'закрыт')),
    addons_separate        boolean NOT NULL DEFAULT true,    -- платные допы отдельным ДС № n-01
    bonus_addons           varchar(8) NOT NULL DEFAULT 'zero' CHECK (bonus_addons IN ('zero', 'hide')),
    ds_by_brand            boolean NOT NULL DEFAULT true,    -- группировка строк ДС
    ds_by_service          boolean NOT NULL DEFAULT true,
    upd_by_brand           boolean NOT NULL DEFAULT true,    -- группировка закрывающих: комплект = одна УПД
    upd_by_service         boolean NOT NULL DEFAULT false,
    created_by             integer REFERENCES users(id),
    created_at             timestamp NOT NULL DEFAULT now(),
    updated_at             timestamp
);
CREATE INDEX IF NOT EXISTS ix_master_deals_contract_period ON master_deals (contract_id, period);

CREATE TABLE IF NOT EXISTS master_deal_items (
    id              serial PRIMARY KEY,
    master_deal_id  integer NOT NULL REFERENCES master_deals(id) ON DELETE CASCADE,
    deal_id         integer NOT NULL UNIQUE REFERENCES sales_deals(id),   -- сделка — максимум в одном пакете
    added_by        integer REFERENCES users(id),
    added_at        timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_master_deal_items_master ON master_deal_items (master_deal_id);

-- 4. ДС пакета: к какой мастер-сделке и какой вид — основные (№ n), допы (№ n-01) или всё одним ДС.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS master_deal_id integer REFERENCES master_deals(id);
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS kind varchar(8);
DO $$ BEGIN
  ALTER TABLE sales_annexes ADD CONSTRAINT sales_annexes_kind_check CHECK (kind IS NULL OR kind IN ('main', 'addons', 'all'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS ix_sales_annexes_master ON sales_annexes (master_deal_id);

-- 5. Комплекты закрывающих: один комплект = одна УПД = одно основание; № УПД сквозной в рамках мастер-сделки.
CREATE TABLE IF NOT EXISTS master_deal_upds (
    id              serial PRIMARY KEY,
    master_deal_id  integer NOT NULL REFERENCES master_deals(id) ON DELETE CASCADE,
    upd_no          integer NOT NULL,
    annex_id        integer REFERENCES sales_annexes(id),
    brand           varchar(200),          -- ключ группы; пусто — без деления
    service         varchar(200),
    net             numeric(14,2) NOT NULL DEFAULT 0,
    vat             numeric(14,2) NOT NULL DEFAULT 0,
    gross           numeric(14,2) NOT NULL DEFAULT 0,
    basis_text      text,                  -- основание для закрытия; правится до отправки в 1С
    onec_net        numeric(14,2),         -- сумма, вернувшаяся из 1С — дальше она факт
    onec_at         timestamp,
    created_at      timestamp NOT NULL DEFAULT now(),
    UNIQUE (master_deal_id, upd_no)
);

-- 6. Блок «Итоговая сверка» в карточке сделки — с одноимённой стадии (иначе без разметки он виден всегда).
INSERT INTO sales_stage_blocks (stage_id, block_key)
SELECT s.id, 'closing' FROM sales_stages s WHERE s.name = 'Итоговая сверка'
ON CONFLICT (stage_id, block_key) DO NOTHING;

-- 7. Ручное количество единиц (показов) рядом с ручной суммой: при «Вручную» правятся оба, связаны через цену за единицу МП.
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS ds_manual_volume bigint;

-- 8. «Подтвердить сверку» (дизайн 15.10.2026): подтверждение снимается сменой режима, скидки или ручной суммы;
--    «Собрать ДС» — только по подтверждённой. Цифры фиксирует отправка (sent_at), не подтверждение.
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS confirmed_at timestamp;
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS confirmed_by integer REFERENCES users(id);

-- 9. Раскладка мастер-сделки (дизайн 15.10.2026): последний актуальный № ДС по договору (ДС пакета — от следующего),
--    точечные переносы платных допов в основной ДС и кто сохранил раскладку. К раскладке возвращаются и правят, пока ДС не выпущен.
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS start_no integer;
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS moved jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE master_deals ADD COLUMN IF NOT EXISTS saved_by integer REFERENCES users(id);

-- 10. ДС пакета из раскладки (15.10.2026, docs/ПЛАН_конструктор_ДС_из_мастер-сделки.md): суффикс номера у ДС допов («5-01») и снимок
--     строк раскладки (ДС пакета собирается из него, а не из МП заново). Уникальность номера — с учётом суффикса: «5» и «5-01» уживаются.
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS sub_no varchar(8);
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS rows jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS uq_annex_contract_no_sub ON sales_annexes (contract_id, no, coalesce(sub_no, '')) WHERE no IS NOT NULL;
DROP INDEX IF EXISTS uq_annex_contract_no;   -- заменён uq_annex_contract_no_sub (тот же смысл + суффикс); данные не трогаются

-- 11. Вид ДС (владелец 16.10.2026): «первичный» — выпущен на старте на план (закрывающие по факту, могут быть меньше ДС);
--     «по факту» — выпущен после итоговой сверки (суммы совпадают). Подписан ли — НЕ поле: вычисляется из источников (app/sales/annex_signed.py).
ALTER TABLE sales_annexes ADD COLUMN IF NOT EXISTS issue_kind varchar(8);
DO $$ BEGIN
  ALTER TABLE sales_annexes ADD CONSTRAINT sales_annexes_issue_kind_check CHECK (issue_kind IS NULL OR issue_kind IN ('primary', 'fact'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
UPDATE sales_annexes SET issue_kind = 'fact' WHERE issue_kind IS NULL AND master_deal_id IS NOT NULL;
