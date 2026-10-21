-- Все требования стадий настраиваются по услугам (владелец 14.10.2026: «сразу все»). У пунктов без списка услуг появляется список —
-- все активные услуги (поведение не меняется). Условие цикла («полный цикл» / «контур аккаунта») сохраняется рядом: пункт действует,
-- если услуга в списке И цикл сделки совпадает. Повторно накатываемая: трогает только пункты без списка.
WITH allsvc AS (SELECT jsonb_agg(id ORDER BY sort_order) ids FROM sales_services WHERE is_active)
UPDATE sales_stage_checks c
   SET applies_when = COALESCE(c.applies_when, '{}'::jsonb) || jsonb_build_object('service_ids', (SELECT ids FROM allsvc))
 WHERE NOT (COALESCE(c.applies_when, '{}'::jsonb) ? 'service_ids')
   AND NOT (COALESCE(c.applies_when, '{}'::jsonb) ? 'service_id');
