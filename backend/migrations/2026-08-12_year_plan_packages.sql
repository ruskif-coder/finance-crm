-- Фаза 1: годовой план как пакет/группировка + жёсткий линк сделок.
-- Идемпотентно (IF NOT EXISTS / WHERE plan_id IS NULL). Локально:
--   docker exec -i finance_db psql -U finance_user -d finance < backend/migrations/2026-08-12_year_plan_packages.sql
-- Бэкап перед запуском:
--   docker exec -t finance_db pg_dump -U finance_user finance > backups/before_year_plan_packages.sql

BEGIN;

-- 1. Таблица планов/пакетов (create_all тоже создаст её при рестарте, но фиксируем явно).
CREATE TABLE IF NOT EXISTS sales_year_plans (
    id                 SERIAL PRIMARY KEY,
    advertiser_id      INTEGER REFERENCES sales_advertisers(id),
    year               INTEGER NOT NULL,
    title              VARCHAR,
    account_manager_id INTEGER REFERENCES sales_reps(id),
    sales_rep_id       INTEGER REFERENCES sales_reps(id),
    created_by         INTEGER REFERENCES users(id),
    created_at         TIMESTAMP DEFAULT now(),
    updated_at         TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sales_year_plans_advertiser ON sales_year_plans(advertiser_id);
CREATE INDEX IF NOT EXISTS ix_sales_year_plans_year       ON sales_year_plans(year);
CREATE INDEX IF NOT EXISTS ix_sales_year_plans_rep        ON sales_year_plans(sales_rep_id);

-- 2. Новые колонки на строке плана.
ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS plan_id          INTEGER REFERENCES sales_year_plans(id);
ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS brief            JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS service_forecast JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS ix_sales_year_plan_lines_plan ON sales_year_plan_lines(plan_id);

-- 3. Жёсткий линк сделки на ячейку плана (строка × месяц).
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS year_plan_line_id INTEGER REFERENCES sales_year_plan_lines(id);
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS plan_month        INTEGER;
CREATE INDEX IF NOT EXISTS ix_sales_deals_year_plan_line ON sales_deals(year_plan_line_id);

-- 4. Бэкфилл: под каждую уникальную (advertiser_id, year, sales_rep_id) существующих
--    строк без плана создаём дефолтный план с автозаголовком, затем проставляем plan_id.
INSERT INTO sales_year_plans (advertiser_id, year, sales_rep_id, title, created_at)
SELECT DISTINCT l.advertiser_id, l.year, l.sales_rep_id,
       COALESCE(a.short_name, a.name, 'Без рекламодателя') || ' · ' || l.year::text,
       now()
FROM sales_year_plan_lines l
LEFT JOIN sales_advertisers a ON a.id = l.advertiser_id
WHERE l.plan_id IS NULL;

UPDATE sales_year_plan_lines l
SET plan_id = p.id
FROM sales_year_plans p
WHERE l.plan_id IS NULL
  AND p.advertiser_id IS NOT DISTINCT FROM l.advertiser_id
  AND p.year          =  l.year
  AND p.sales_rep_id  IS NOT DISTINCT FROM l.sales_rep_id;

COMMIT;
