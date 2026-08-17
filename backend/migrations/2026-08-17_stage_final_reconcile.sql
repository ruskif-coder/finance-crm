-- Новая стадия «Итоговая сверка» в этапе «Услуги». Согласовано с владельцем 2026-08-17.
--
-- Цепочка после правки:
--   Бронь → Готовятся к старту → В размещении → Предварительная сверка →
--   Итоговая сверка → (ДО: Подготовка ДС …)
--
-- stage_key = 'launch' — то есть слой денег «реализуемые», по прямому решению владельца:
-- сверка ещё не закрытие, деньги на ней в работе, а не факт. Это решение о ДЕНЬГАХ,
-- не только о порядке: с 'closing' те же сделки ушли бы в фактические и сдвинули бы
-- и ДДС, и P&L. money_layer хранится строкой рядом — он производный от stage_key
-- (см. app/sales/stages.py), но джойны читают колонку.
--
-- Битрикс-привязки нет намеренно: в портале такой стадии не существует, движение
-- туда — наше внутреннее. Появится в Битриксе — привяжут через настройки стадий.
--
-- Повторный накат безопасен: вставка идёт только если стадии с таким именем в этапе нет.

BEGIN;

DO $$
DECLARE
    -- НЕ phase_id: переменная с именем колонки делает условие «phase_id = phase_id»
    -- неоднозначным, и PL/pgSQL отказывается его выполнять.
    ph_id integer;
    prev_order integer;
BEGIN
    SELECT id INTO ph_id FROM sales_stage_phases WHERE sort_order = 1;   -- «Услуги»
    IF ph_id IS NULL THEN
        RAISE EXCEPTION 'Этап «Услуги» не найден';
    END IF;

    IF EXISTS (SELECT 1 FROM sales_stages WHERE phase_id = ph_id AND name = 'Итоговая сверка') THEN
        RAISE NOTICE 'Стадия «Итоговая сверка» уже есть — пропуск';
        RETURN;
    END IF;

    SELECT sort_order INTO prev_order FROM sales_stages
     WHERE phase_id = ph_id AND name = 'Предварительная сверка';
    IF prev_order IS NULL THEN
        RAISE EXCEPTION 'Стадия «Предварительная сверка» не найдена — порядок задать не от чего';
    END IF;

    -- Освобождаем позицию: всё, что стояло после предварительной сверки (терминальный
    -- срыв), сдвигается вниз. Иначе новая стадия встала бы вровень с ним и порядок
    -- решался бы по id — то есть случайно.
    UPDATE sales_stages SET sort_order = sort_order + 1
     WHERE phase_id = ph_id AND sort_order > prev_order;

    INSERT INTO sales_stages (phase_id, name, sort_order, stage_key, money_layer,
                              is_terminal, is_lost, requires_media_plan, sla_days)
    VALUES (ph_id, 'Итоговая сверка', prev_order + 1, 'launch', 'реализуемые',
            false, false, true, 3);

    RAISE NOTICE 'Стадия «Итоговая сверка» добавлена на позицию %', prev_order + 1;
END $$;

COMMIT;
