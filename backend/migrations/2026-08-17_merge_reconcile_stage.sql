-- Откат разделения сверки: «Предварительная сверка» и «Итоговая сверка» — ОДНА стадия
-- (уточнение владельца 2026-08-17, сразу после 2026-08-17_stage_final_reconcile.sql).
--
-- Оставляем одну строку и называем её «Итоговая сверка» — так стадию назвал владелец,
-- когда описывал этот участок последним. Смысл её тот же, что раньше нёс «Предварительная
-- сверка»: размещение закончилось, трафик отчитался, финализируем цифры и готовим
-- документальное закрытие. Слой денег — «реализуемые» (launch), как решено: сверка
-- не закрытие, деньги на ней в работе.
--
-- Переименовываем существующую строку (id 8), а добавленную вчера (id 17) удаляем:
-- так меньше движений — на id 8 исторически ссылались привязки и порядок, а новая
-- строка ничем не обросла. Обе на момент правки пустые: 0 сделок, 0 записей истории,
-- иначе миграция упадёт (предохранитель ниже), а не перевесит сделки молча.

BEGIN;

DO $$
DECLARE
    ph_id integer;
    keep_id integer;
    drop_id integer;
    n_deals integer;
    n_hist integer;
BEGIN
    SELECT id INTO ph_id FROM sales_stage_phases WHERE sort_order = 1;   -- «Услуги»

    SELECT id INTO keep_id FROM sales_stages
     WHERE phase_id = ph_id AND name IN ('Предварительная сверка', 'Итоговая сверка')
     ORDER BY sort_order LIMIT 1;
    SELECT id INTO drop_id FROM sales_stages
     WHERE phase_id = ph_id AND name IN ('Предварительная сверка', 'Итоговая сверка')
       AND id <> keep_id ORDER BY sort_order DESC LIMIT 1;

    IF keep_id IS NULL THEN
        RAISE EXCEPTION 'Стадия сверки не найдена';
    END IF;

    IF drop_id IS NOT NULL THEN
        SELECT count(*) INTO n_deals FROM sales_deals WHERE our_stage_id = drop_id;
        SELECT count(*) INTO n_hist FROM sales_deal_stage_history
         WHERE to_stage_id = drop_id OR from_stage_id = drop_id;
        IF n_deals > 0 OR n_hist > 0 THEN
            RAISE EXCEPTION 'На удаляемой стадии % сделок и % записей истории — перенесите движением', n_deals, n_hist;
        END IF;
        DELETE FROM sales_stages WHERE id = drop_id;
        -- Порядок снова плотный: терминальный срыв возвращается на освободившуюся позицию.
        UPDATE sales_stages SET sort_order = sort_order - 1
         WHERE phase_id = ph_id AND sort_order > (SELECT sort_order FROM sales_stages WHERE id = keep_id);
        RAISE NOTICE 'Лишняя стадия сверки (id=%) удалена', drop_id;
    END IF;

    UPDATE sales_stages SET name = 'Итоговая сверка', stage_key = 'launch',
           money_layer = 'реализуемые', sla_days = 3, requires_media_plan = true
     WHERE id = keep_id;
    RAISE NOTICE 'Единая стадия сверки: id=%, «Итоговая сверка»', keep_id;
END $$;

COMMIT;
