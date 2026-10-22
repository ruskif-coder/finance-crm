-- «Статусы продаж» (владелец 22.10.2026: «да, делай»): матрица клиент × месяц × вероятность — замена листа Excel продаж.
-- Состав согласован с владельцем 22.10.2026. Повтор безопасен.

-- Строка «Статусов продаж» на бренд: встречи и комментарии — то, чего нет в сделке и что продажи вели в Excel.
-- Одна текущая запись на пару «рекламодатель + бренд» (как строка Excel); история правок — в журнале действий.
CREATE TABLE IF NOT EXISTS sales_status_notes (
    id             serial PRIMARY KEY,
    advertiser_id  integer REFERENCES sales_advertisers(id) ON DELETE CASCADE,
    brand_id       integer REFERENCES sales_brands(id) ON DELETE CASCADE,      -- пусто — строка уровня рекламодателя
    client_name    varchar(300),                                               -- клиент из Excel вне справочника (только без рекламодателя)
    meet_brand     varchar(12) CONSTRAINT ck_sales_status_note_meet_brand CHECK (meet_brand IN ('предложена', 'подтверждена')),   -- пусто — встречи нет
    meet_agency    varchar(12) CONSTRAINT ck_sales_status_note_meet_agency CHECK (meet_agency IN ('предложена', 'подтверждена')),
    comment_sales  text,
    comment_head   text,
    from_excel     text[] NOT NULL DEFAULT '{}',  -- поля, ещё хранящие значение из Excel (метка «из Excel»); правка поля убирает его
    updated_by     integer REFERENCES users(id) ON DELETE SET NULL,
    updated_at     timestamp NOT NULL DEFAULT now(),
    CONSTRAINT ck_sales_status_note_owner CHECK ((advertiser_id IS NOT NULL) <> (client_name IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_status_note_brand
    ON sales_status_notes (advertiser_id, coalesce(brand_id, 0)) WHERE advertiser_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_status_note_client
    ON sales_status_notes (lower(client_name)) WHERE client_name IS NOT NULL;

-- Дата статуса, поставленная вручную в ячейке «Дата». Пусто — дата считается сама: история стадий, иначе последняя правка.
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS status_date_manual date;

-- Право `sales_status` (просмотр / правка), область «свои/все» — от реестра сделок. Бэкфилл по решению владельца:
-- у кого просмотр реестра сделок — просмотр, у кого правка — правка. Один раз, пока у права нет ни одной строки.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'sales_status') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT rp.role_id, 'sales_status', rp.can_view, 0, rp.can_edit, 0, 0, 0, coalesce(rp.deals_scope, 'all')
          FROM role_permissions rp
         WHERE rp.section = 'sales_registry' AND rp.can_view = 1;
    END IF;
END $$;
