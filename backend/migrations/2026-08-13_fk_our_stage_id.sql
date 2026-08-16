-- FK sales_deals.our_stage_id -> sales_stages.id
-- Причина: колонка была без внешнего ключа, а PUT /stage-catalog удалял стадии, не
-- проверяя использование. Удаление стадии оставляло сделки с указателем в никуда —
-- молча, без ошибки. Проверка добавлена и в код (save_stage_catalog), FK закрывает
-- прямые правки в БД и любые будущие точки удаления.
--
-- Тот же DO-блок выполняется на старте бэкенда (app/main.py), файл — для ручного
-- применения на сервере и как след изменения схемы.
--
-- Перед применением убедиться, что висячих ссылок нет (должно вернуть 0 строк):
--   select d.id, d.our_stage_id from sales_deals d
--     left join sales_stages s on s.id = d.our_stage_id
--    where d.our_stage_id is not null and s.id is null;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sales_deals_our_stage_id_fkey') THEN
        ALTER TABLE sales_deals ADD CONSTRAINT sales_deals_our_stage_id_fkey
            FOREIGN KEY (our_stage_id) REFERENCES sales_stages(id);
    END IF;
END $$;
