-- Пустые воронки — пережиток Битрикса (владелец 14.10.2026: «воронки где 0 сделок можно удалять»).
-- Удаляются ТОЛЬКО воронки без сделок: ни по имени (`sales_deals.pipeline`), ни как воронка реализации, ни по ссылке из наших стадий.
-- Строки сопоставления битриксовых стадий уходят каскадом (FK ON DELETE CASCADE). Повторный прогон ничего не делает.
DELETE FROM sales_pipelines p
 WHERE NOT EXISTS (SELECT 1 FROM sales_deals d WHERE d.pipeline = p.name)
   AND NOT EXISTS (SELECT 1 FROM sales_deals d WHERE d.realization_pipeline_id = p.id)
   AND NOT EXISTS (SELECT 1 FROM sales_stages s WHERE s.bitrix_pipeline_id = p.id);
