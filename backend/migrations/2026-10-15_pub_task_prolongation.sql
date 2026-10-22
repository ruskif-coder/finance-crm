-- Пометка «пролонгация» у задания площадки (владелец 15.10.2026): сделка, созданная
-- «Скопировать сделку», хранит sales_deals.prolonged_from_id. Площадка получает креатив
-- копии на (повторное) согласование и должна видеть, что это продолжение уже
-- согласованной кампании, а не новый запуск. Колонка is_prolongation добавлена
-- ПОСЛЕДНЕЙ — CREATE OR REPLACE VIEW не меняет порядок существующих колонок.
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
    st.advertiser_url,
    r.asked_at,
    t.id AS target_id,
    st.url_requested_at,
    st.url_request_text,
    t.surface_kind,
    s.rights_letter_name,
    s.rights_letter_size,
    st.deeplink_url AS app_url,
    d.prolonged_from_id IS NOT NULL AS is_prolongation
   FROM launch_prep_review r
     JOIN launch_prep_pair p ON p.id = r.pair_id
     JOIN launch_prep_creative_set s ON s.id = p.set_id
     JOIN launch_prep_target t ON t.id = p.target_id
     LEFT JOIN launch_prep_set_target st ON st.set_id = p.set_id AND st.target_id = p.target_id
     JOIN sales_publishers pb ON pb.id = t.publisher_id
     JOIN sales_deals d ON d.id = s.deal_id
     LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
     LEFT JOIN sales_brands br ON br.id = d.brand_id
  WHERE r.kind::text = 'площадка'::text AND r.verdict IS NULL AND p.withdrawn_at IS NULL AND (t.publisher_id = ANY (pub.allowed_publisher_ids()));

GRANT SELECT ON pub.task_v1 TO cabinet;
