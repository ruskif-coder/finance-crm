-- «Обязательное на сборке» — по услугам (владелец 14.10.2026): у пунктов стадий Бронь / Готовятся к старту / В размещении условие
-- «для услуг: […]» вместо «полный цикл» / «все». Экран — «Справочники → Услуги». еФарм — «100 % всего»: все пункты сборки.
-- Блокирует или предупреждает — у самого пункта, одинаково для всех услуг. Повторно накатываемая (условия выставляются, не дописываются).
WITH asm AS (SELECT id FROM sales_stages WHERE name IN ('Бронь', 'Готовятся к старту', 'В размещении')),
     allsvc AS (SELECT jsonb_agg(id ORDER BY sort_order) ids FROM sales_services WHERE is_active)
UPDATE sales_stage_checks c SET applies_when = jsonb_build_object('service_ids', (SELECT ids FROM allsvc))
 WHERE c.stage_id IN (SELECT id FROM asm) AND c.applies_when IS NULL;

WITH asm AS (SELECT id FROM sales_stages WHERE name IN ('Бронь', 'Готовятся к старту', 'В размещении'))
UPDATE sales_stage_checks c SET applies_when = jsonb_build_object('service_ids', jsonb_build_array((SELECT id FROM sales_services WHERE name = 'еФарм')))
 WHERE c.stage_id IN (SELECT id FROM asm) AND c.applies_when = '{"closing_flow": "полный цикл"}'::jsonb;

-- еФарм — всё: базовые пункты сделки на «Готовятся к старту» (блокируют) и пиксель Weborama на «В размещении» — там, где он заказан.
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, applies_when, sort_order)
SELECT st.id, k.key, k.blk, jsonb_build_object('service_ids', jsonb_build_array(s.id)), k.ord
  FROM sales_stages st, sales_services s,
       (VALUES ('mp_linked', true, 1), ('service_set', true, 2), ('period_set', true, 3)) AS k(key, blk, ord)
 WHERE st.name = 'Готовятся к старту' AND s.name = 'еФарм'
ON CONFLICT (stage_id, check_key) DO NOTHING;
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, applies_when, sort_order)
SELECT st.id, 'weborama_pixel', false, jsonb_build_object('service_ids', jsonb_build_array(s.id), 'weborama_pixel', true), 20
  FROM sales_stages st, sales_services s WHERE st.name = 'В размещении' AND s.name = 'еФарм'
ON CONFLICT (stage_id, check_key) DO NOTHING;
