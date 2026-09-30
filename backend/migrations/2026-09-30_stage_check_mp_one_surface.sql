-- Алерт «web и app одной услуги — две отдельные сделки» (владелец 30.09.2026).
-- Проверка `mp_one_surface` (app/sales/stage_checks.py) на стадиях «Бронь» и
-- «Готовятся к старту»; не запирающая — предупреждение в чек-листе и очереди аккаунта.
-- Повторный накат ничего не меняет (уникальность stage_id + check_key).
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, sort_order, hint)
SELECT s.id, 'mp_one_surface', false, 0,
       'Web и app одной услуги — две отдельные сделки: разделите медиаплан'
  FROM sales_stages s
 WHERE s.name IN ('Бронь', 'Готовятся к старту')
ON CONFLICT (stage_id, check_key) DO NOTHING;
