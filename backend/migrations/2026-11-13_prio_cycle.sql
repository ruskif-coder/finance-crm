-- Свой цикл приоритезации (владелец 13.11.2026: «действительно» — полный цикл запирал её проверками DSP, контур аккаунта
-- терял факт из статистики сервиса). Запуск и завершение — кнопками аккаунта, трафик не участвует; РК заводится как носитель
-- факта; факт — из статистики сервиса или, по решению аккаунта на итоговой сверке, из загруженного файла.

-- 1. Третий вид цикла у воронки реализации.
ALTER TABLE sales_pipelines DROP CONSTRAINT IF EXISTS sales_pipelines_closing_flow_check;
ALTER TABLE sales_pipelines ADD CONSTRAINT sales_pipelines_closing_flow_check
  CHECK (closing_flow IS NULL OR closing_flow IN ('полный цикл', 'контур аккаунта', 'приоритезация'));

-- 2. Откуда факт площадки запроса: из статистики сервиса (по умолчанию) или из итогового файла, загруженного аккаунтом на
--    итоговой сверке («переключатель уже на итоговой сверке, у аккаунта решение подгружать или нет»). При «файл» ночной сбор
--    перестаёт писать факт этой площадки (снимки для автостопа сохраняет).
ALTER TABLE prio_placements ADD COLUMN IF NOT EXISTS fact_source VARCHAR(16) NOT NULL DEFAULT 'сервис';
DO $$ BEGIN
  ALTER TABLE prio_placements ADD CONSTRAINT prio_placements_fact_source_check CHECK (fact_source IN ('сервис', 'файл'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
COMMENT ON COLUMN prio_placements.fact_source IS
  'Откуда факт площадки: сервис — ночная статистика системы приоритезации; файл — итог, загруженный аккаунтом на сверке.';

-- 3. Воронка «Приоритезация» с этим циклом и услуга на ней.
INSERT INTO sales_pipelines (name, sort_order, is_active, is_tracked, closing_flow)
SELECT 'Приоритезация', COALESCE((SELECT max(sort_order) FROM sales_pipelines), 0) + 1, true, true, 'приоритезация'
 WHERE NOT EXISTS (SELECT 1 FROM sales_pipelines WHERE name = 'Приоритезация');
UPDATE sales_services SET realization_pipeline_id = (SELECT id FROM sales_pipelines WHERE name = 'Приоритезация')
 WHERE name = 'Приоритезация' AND realization_pipeline_id IS NULL;

-- 4. Разметка требований для цикла «приоритезация» (данные, не схема). Вход в «В размещении» — хотя бы одна площадка идёт;
--    вход в ДО — сделка завершена аккаунтом и факт есть по всем запущенным площадкам.
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, applies_when, sort_order)
SELECT st.id, x.key, true, '{"closing_flow": "приоритезация"}'::jsonb, x.ord
  FROM sales_stages st
  JOIN (VALUES ('В размещении', 'prio_live', 50)) AS x(stage, key, ord) ON x.stage = st.name
ON CONFLICT (stage_id, check_key) DO NOTHING;

INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, applies_when, sort_order)
SELECT st.id, 'prio_fact_complete', true, '{"closing_flow": "приоритезация"}'::jsonb, 60
  FROM sales_stages st WHERE st.name = 'Подготовка ДС'
ON CONFLICT (stage_id, check_key) DO NOTHING;

-- «Сделка завершена аккаунтом» — на всех стадиях ДО, где она стоит у контура аккаунта: для приоритезации — та же строка
-- с её циклом. Строка одна на (стадия, проверка), поэтому условие расширяется списком циклов, а не второй строкой.
UPDATE sales_stage_checks SET applies_when = jsonb_set(applies_when, '{closing_flow}', '["контур аккаунта", "приоритезация"]'::jsonb)
 WHERE check_key = 'account_finished' AND applies_when->>'closing_flow' = 'контур аккаунта';
