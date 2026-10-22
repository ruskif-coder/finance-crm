-- Воронка реализации — явно у сделок В РАБОТЕ (Бронь … Итоговая сверка), где её нет: по воронке их услуги (владелец 14.10.2026).
-- Цикл и так выводился от услуги; так он виден в данных и не зависит от того, поменяют ли потом воронку услуги. Только пустые, повторно — ничего.
UPDATE sales_deals d SET realization_pipeline_id = s.realization_pipeline_id
  FROM sales_services s, sales_stages st
 WHERE s.id = d.service_id AND st.id = d.our_stage_id
   AND d.realization_pipeline_id IS NULL AND s.realization_pipeline_id IS NOT NULL
   AND st.name IN ('Бронь', 'Готовятся к старту', 'В размещении', 'Итоговая сверка');
