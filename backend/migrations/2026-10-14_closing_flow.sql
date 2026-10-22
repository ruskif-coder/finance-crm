-- Цикл — у ВОРОНКИ РЕАЛИЗАЦИИ, услуга указывает свою воронку (владелец 14.10.2026; схема утверждена).
-- «полный цикл» — трафик, DSP/Adfox, факт оттуда (Pharm); «контур аккаунта» — запуск и завершение кнопками аккаунта, трафик сделку не ведёт,
-- факт в сверке вручную («Прочие продукты»). Воронка без цикла — не воронка реализации (сопоставление стадий Битрикса, история).
-- У сделки цикл берётся из её воронки реализации, нет её — из воронки услуги, нет и её — полный цикл. Повторно накатываемая.
ALTER TABLE sales_pipelines ADD COLUMN IF NOT EXISTS closing_flow VARCHAR(20)
    CHECK (closing_flow IS NULL OR closing_flow IN ('полный цикл', 'контур аккаунта'));
COMMENT ON COLUMN sales_pipelines.closing_flow IS
  'Цикл воронки реализации: полный цикл (трафик, DSP/Adfox) или контур аккаунта (кнопки аккаунта, факт вручную). Пусто — не воронка реализации';
UPDATE sales_pipelines SET closing_flow = 'полный цикл'     WHERE name = 'Pharm'           AND closing_flow IS NULL;
UPDATE sales_pipelines SET closing_flow = 'контур аккаунта' WHERE name = 'Прочие продукты' AND closing_flow IS NULL;

ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS realization_pipeline_id INTEGER REFERENCES sales_pipelines (id);
COMMENT ON COLUMN sales_services.realization_pipeline_id IS 'Воронка реализации услуги: по умолчанию у сделки, задаёт цикл';
UPDATE sales_services s SET realization_pipeline_id = p.id FROM sales_pipelines p
 WHERE s.realization_pipeline_id IS NULL
   AND ((s.name = 'еФарм' AND p.name = 'Pharm')
     OR (s.name IN ('Альфарм-Таргет', 'Polza', 'OLV') AND p.name = 'Прочие продукты'));

-- Цикл у услуги (заведён утром 14.10 на стенде, на прод не уходил) заменён циклом воронки — колонку убираем.
ALTER TABLE sales_services DROP COLUMN IF EXISTS closing_flow;

-- Polza — в воронку реализации «Прочие продукты», как Альфарм-Таргет и OLV (владелец 14.10.2026: «пользу переводим»).
UPDATE sales_deals d SET realization_pipeline_id = p_other.id
  FROM sales_pipelines p_other, sales_pipelines p_pharm, sales_services s
 WHERE p_other.name = 'Прочие продукты' AND p_pharm.name = 'Pharm' AND s.name = 'Polza'
   AND d.service_id = s.id AND d.realization_pipeline_id = p_pharm.id;

