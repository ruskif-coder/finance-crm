-- Годовой план: несколько сделок в одном месяце.
--
-- В конструкторе услуг месяца появился разделитель «+ сделка»: услуги делятся на
-- группы (products[m][*].deal_idx = 0,1,2…), каждая группа = отдельная сделка.
-- Раньше сделка опознавалась парой (year_plan_line_id, plan_month) — этого больше
-- не хватает, повторный прогон конвейера не отличил бы 2-ю сделку месяца от 1-й.
--
-- Ключ жёсткого линка становится: (year_plan_line_id, plan_month, plan_deal_idx).
-- Все ранее созданные сделки — первая сделка своего месяца, поэтому 0.
--
-- Применение:
--   docker exec -i finance_db psql -U finance_user -d finance < backend/migrations/2026-08-13_plan_deal_idx.sql

ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS plan_deal_idx INTEGER DEFAULT 0;

-- Бэкфилл существующих плановых сделок (созданы до появления групп).
UPDATE sales_deals
   SET plan_deal_idx = 0
 WHERE year_plan_line_id IS NOT NULL
   AND plan_deal_idx IS NULL;

-- Поиск сделки по линку при каждом прогоне конвейера идёт ровно по этой тройке.
CREATE INDEX IF NOT EXISTS ix_sales_deals_plan_link
    ON sales_deals (year_plan_line_id, plan_month, plan_deal_idx);
