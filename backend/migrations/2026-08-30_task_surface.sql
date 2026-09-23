-- Поверхность размещения — в задание кабинета.
--
-- Карточка задания в кабинете печатает `t.surface` с самого начала:
--
--     {[t.service, t.surface].filter(Boolean).join(' · ')}
--
-- но `pub.task_v1` такого поля не отдавала. `filter(Boolean)` молча выбрасывал пустое, и
-- строка схлопывалась в одну услугу — площадка не видела, веб это или приложение. А от
-- этого зависят и требования к материалу, и место размещения, то есть ровно то, по чему
-- она принимает решение. Ошибка ничего не ломала и потому прожила до 30.08.2026, пока в
-- очередь не попало первое задание по приложению и не оказалось неотличимо от вебовых.
--
-- Колонка дописывается В КОНЕЦ: `CREATE OR REPLACE VIEW` не разрешает менять порядок и
-- имена существующих. Состав контракта закреплён прибором `tests/test_cabinet_contract.py`
-- со строгим сравнением — список там правится тем же изменением, иначе он падает.

-- ПОВТОРНЫЙ НАКАТ (23.09.2026): только пока представление не расширено поздней миграцией
-- (признак — `rights_letter_name` из 2026-09-07_rights_letter.sql). Иначе повтор падал
-- с «cannot drop columns from view» и срывал накат всей цепочки (аудит 23.09.2026).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = 'pub' AND table_name = 'task_v1'
                   AND column_name = 'rights_letter_name') THEN
    CREATE OR REPLACE VIEW pub.task_v1 WITH (security_barrier) AS
        SELECT p.id AS task_id,
            t.publisher_id,
            pb.name AS publisher_name,
            pb.domain AS publisher_domain,
            pb.tech_requirements,
            s.id AS creative_id,
            s.no AS creative_no,
            s.title AS creative_title,
            s.form,
            COALESCE(adv.short_name, adv.name) AS advertiser,
            br.name AS brand,
            d.product AS service,
            COALESCE(t.period_from, d.period_from) AS period_from,
            COALESCE(t.period_to, d.period_to) AS period_to,
            t.advertiser_url,
            r.asked_at,
            t.id AS target_id,
            t.url_requested_at,
            t.url_request_text,
            t.surface_kind
           FROM launch_prep_review r
             JOIN launch_prep_pair p ON p.id = r.pair_id
             JOIN launch_prep_creative_set s ON s.id = p.set_id
             JOIN launch_prep_target t ON t.id = p.target_id
             JOIN sales_publishers pb ON pb.id = t.publisher_id
             JOIN sales_deals d ON d.id = s.deal_id
             LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
             LEFT JOIN sales_brands br ON br.id = d.brand_id
          WHERE r.kind::text = 'площадка'::text
            AND r.verdict IS NULL
            AND (t.publisher_id = ANY (pub.allowed_publisher_ids()));
  END IF;
END $$;

GRANT SELECT ON pub.task_v1 TO cabinet;
