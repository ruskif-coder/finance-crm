-- Уровень пункта — по услуге (владелец 14.10.2026: «не требуется — уведомляет — требуется» в каждой клетке матрицы).
-- `applies_when.blocking_service_ids` — услуги, для которых пункт ЗАПИРАЕТ переход; остальные из `service_ids` — только уведомление.
-- Заполняется из прежнего общего `is_blocking` строки, поведение не меняется. Повторно накатываемая: трогает только строки без списка.
UPDATE sales_stage_checks c
   SET applies_when = c.applies_when || jsonb_build_object('blocking_service_ids',
         CASE WHEN c.is_blocking THEN COALESCE(c.applies_when -> 'service_ids', '[]'::jsonb) ELSE '[]'::jsonb END)
 WHERE c.applies_when ? 'service_ids' AND NOT (c.applies_when ? 'blocking_service_ids');
