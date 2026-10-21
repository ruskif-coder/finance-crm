-- Виза медиаплана (владелец 15.10.2026): две отжатые «проверено» в конструкторе (размещения + прогноз) — это и есть виза.
-- Раньше она нигде не хранилась (только гейт сохранения). Ставится при сохранении из конструктора с обеими отметками; у планов,
-- созданных системой (годовой план, продление), пусто — сделке нужна виза. Повторно накатываемая.
ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP;
ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS verified_by INTEGER REFERENCES users (id);
COMMENT ON COLUMN sales_media_plans.verified_at IS 'Виза: когда план проверен в конструкторе (обе отметки «проверено»). Пусто — план создан системой и не проверен';

-- Задним числом: планы, чьи сделки уже ушли с первой стадии, считаем завизированными — их проверили, когда двигали сделку.
-- Иначе алерт «требуется виза» загорелся бы разом на всех живых сделках. Только пустые, повторно — ничего.
UPDATE sales_media_plans mp SET verified_at = COALESCE(mp.created_at, now())
  FROM sales_deals d, sales_stages st
 WHERE d.id = mp.deal_id AND st.id = d.our_stage_id AND mp.verified_at IS NULL
   AND st.id <> (SELECT s2.id FROM sales_stages s2 JOIN sales_stage_phases ph ON ph.id = s2.phase_id
                  WHERE NOT s2.is_terminal ORDER BY ph.sort_order, s2.sort_order LIMIT 1);

-- Пункт матрицы «Виза МП» на «Готовятся к старту»: всем активным услугам — «уведомляет»; блокировку админ включает в матрице.
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, applies_when, sort_order)
SELECT st.id, 'mp_verified', false,
       jsonb_build_object('service_ids', (SELECT jsonb_agg(id ORDER BY sort_order) FROM sales_services WHERE is_active),
                          'blocking_service_ids', '[]'::jsonb), 2
  FROM sales_stages st WHERE st.name = 'Готовятся к старту'
ON CONFLICT (stage_id, check_key) DO NOTHING;
