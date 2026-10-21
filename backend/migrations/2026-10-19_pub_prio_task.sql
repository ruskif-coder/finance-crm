-- Кабинет площадки: запросы на приоритезацию в «Требует вашего решения» (владелец 19.10.2026). Видит только СВОИ площадки
-- (pub.allowed_publisher_ids), только запросы «у площадки». Денег нет: цель — в показах, суммы не отдаются.
-- Повторно накатываемая.
CREATE OR REPLACE VIEW pub.prio_task_v1 WITH (security_barrier) AS
SELECT pp.id AS prio_id,
       pp.publisher_id,
       pb.name AS publisher_name,
       COALESCE(adv.short_name, adv.name) AS advertiser,
       br.name AS brand,
       r.product_name,
       r.date_start,
       r.date_end,
       r.target_competitors,
       r.target_mnn,
       r.target_meta,
       pp.goal_imp,
       pp.erid,
       pp.product_url AS landing,
       pp.product_id AS sku,
       pp.comment AS remark,
       pp.sent_at
  FROM prio_placements pp
  JOIN prio_requests r ON r.id = pp.request_id
  JOIN sales_deals d ON d.id = r.deal_id
  JOIN sales_publishers pb ON pb.id = pp.publisher_id
  LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
  LEFT JOIN sales_brands br ON br.id = d.brand_id
 WHERE pp.status = 'у площадки' AND pp.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.prio_task_v1 TO cabinet;
