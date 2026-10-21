-- Кабинет площадки, 19.10.2026: факт площадки учитывает источник `prio` — статистику системы приоритезации (`app/prio/stats`).
-- Список источников = `app/ad/stat_sources.OWN` (прибор `test_stat_sources::test_views_over_the_table_count_only_our_counter`).
-- «Block SIMB» вычитается только из показов DSP: Adfox и Приоритезация его не содержат — из вычета исключены оба.
-- Определение — живое из каталога (после 2026-10-03_pub_fact_minus_block_simb.sql), изменены только два списка источников.
-- Повторно накатываемая.
CREATE OR REPLACE VIEW pub.campaign_v1 WITH (security_barrier) AS
SELECT t.id AS placement_id,
    t.publisher_id,
    pb.domain AS site,
    COALESCE(adv.short_name, adv.name, '—'::character varying)::text || COALESCE(' · '::text || NULLIF(br.name::text, ''::text), ''::text) AS brand,
    d.product AS service,
    t.surface_kind AS surface,
    COALESCE(t.period_from, d.period_from) AS date_from,
    COALESCE(t.period_to, d.period_to) AS date_to,
    COALESCE(pl.plan_show, 0::double precision)::bigint AS plan,
    COALESCE(st.shows, 0::numeric)::bigint AS fact,
    COALESCE(pb.cpm_contract, 0::double precision)::numeric AS cpm,
    COALESCE(er.erid, ''::character varying) AS erid,
        CASE
            WHEN rej.pair_id IS NOT NULL THEN 'отказ'::text
            WHEN "dec".declined AND NOT "dec".live THEN 'отказ'::text
            WHEN t.state::text = 'отказ площадки'::text THEN 'отказ'::text
            WHEN pl.status::text = 'запущен'::text THEN 'в размещении'::text
            WHEN pl.status::text = 'пауза'::text THEN 'пауза'::text
            WHEN pl.status::text = 'завершена'::text THEN 'завершён'::text
            WHEN c.status::text = 'запущена'::text THEN 'в размещении'::text
            WHEN c.status::text = ANY (ARRAY['пауза'::character varying::text, 'остановлена'::character varying::text]) THEN 'пауза'::text
            WHEN c.status::text = 'окончена'::text THEN 'завершён'::text
            WHEN COALESCE(t.period_to, d.period_to) < CURRENT_DATE THEN 'завершён'::text
            WHEN t.state::text = ANY (ARRAY['завершён'::character varying::text, 'сверка завершена'::character varying::text, 'архив'::character varying::text]) THEN 'завершён'::text
            WHEN t.state::text = ANY (ARRAY['согласован'::character varying::text, 'ерид получен'::character varying::text, 'заведён в DSP'::character varying::text, 'в размещении'::character varying::text]) THEN 'ждёт старта'::text
            ELSE 'ждёт согласования'::text
        END AS status,
    (EXISTS ( SELECT 1
           FROM publisher_request pr
          WHERE pr.kind = 'сверка'::text AND pr.verdict IS NOT NULL AND pr.publisher_id = t.publisher_id AND (pr.deal_id IS NULL OR pr.deal_id = t.deal_id) AND pr.period = to_char(COALESCE(t.period_from, d.period_from)::timestamp with time zone, 'YYYY-MM'::text))) AS reconciled
   FROM launch_prep_target t
     JOIN sales_publishers pb ON pb.id = t.publisher_id
     JOIN sales_deals d ON d.id = t.deal_id
     LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
     LEFT JOIN sales_brands br ON br.id = d.brand_id
     LEFT JOIN ad_campaign c ON c.deal_id = d.id
     LEFT JOIN ad_campaign_placement pl ON pl.campaign_id = c.id AND pl.publisher_id = t.publisher_id
     LEFT JOIN LATERAL ( SELECT sum(dd.own) - round(COALESCE(sum(
                CASE
                    WHEN tt.tot > 0 AND kb.k > 0 THEN LEAST(dd.dsp::numeric, kb.k::numeric * dd.dsp::numeric / tt.tot::numeric)
                    ELSE 0::numeric
                END), 0::numeric)) AS shows
           FROM ( SELECT s.date,
                    sum(s.shows) AS own,
                    COALESCE(sum(s.shows) FILTER (WHERE s.source::text <> ALL (ARRAY['adfox'::text, 'prio'::text])), 0::bigint) AS dsp
                   FROM ad_campaign_stat s
                  WHERE s.campaign_id = c.id AND s.placement_id = pl.id AND (s.source::text = ANY (ARRAY['adfox'::character varying::text, 'demo'::character varying::text, 'dsp'::character varying::text, 'manual'::character varying::text, 'ms'::character varying::text, 'prio'::character varying::text]))
                  GROUP BY s.date) dd
             LEFT JOIN LATERAL ( SELECT sum(b.shows) AS k
                   FROM dsp_block_stat b
                  WHERE b.publisher_id = t.publisher_id AND b.date = dd.date) kb ON true
             LEFT JOIN LATERAL ( SELECT sum(s2.shows) AS tot
                   FROM ad_campaign_stat s2
                     JOIN ad_campaign_placement p2 ON p2.id = s2.placement_id
                  WHERE p2.publisher_id = t.publisher_id AND s2.date = dd.date AND (s2.source::text = ANY (ARRAY['demo'::character varying::text, 'dsp'::character varying::text, 'manual'::character varying::text, 'ms'::character varying::text]))) tt ON true) st ON true
     LEFT JOIN LATERAL ( SELECT cs.erid
           FROM launch_prep_creative_set cs
             LEFT JOIN launch_prep_pair p2 ON p2.set_id = cs.id AND p2.target_id = t.id
          WHERE cs.deal_id = t.deal_id AND COALESCE(TRIM(BOTH FROM cs.erid), ''::text) <> ''::text AND (COALESCE(cs.erid_source, 'наш'::character varying)::text <> 'наш'::text OR (cs.ord_status::text = ANY (ARRAY['Active'::character varying::text, 'Registering'::character varying::text]))) AND (p2.id IS NOT NULL OR cs.publisher_id = t.publisher_id)
          ORDER BY (p2.id IS NOT NULL) DESC, cs.no DESC
         LIMIT 1) er ON true
     LEFT JOIN LATERAL ( SELECT p.id AS pair_id
           FROM launch_prep_pair p
             JOIN launch_prep_review r ON r.pair_id = p.id
          WHERE p.target_id = t.id AND r.verdict::text = 'отказ'::text
         LIMIT 1) rej ON true
     LEFT JOIN LATERAL ( SELECT bool_or(p.withdraw_kind::text = 'отказ в правках'::text) AS declined,
            bool_or(p.withdrawn_at IS NULL AND p.sent_at IS NOT NULL) AS live
           FROM launch_prep_pair p
          WHERE p.target_id = t.id) "dec" ON true
  WHERE (t.publisher_id = ANY (pub.allowed_publisher_ids())) AND t.archived_at IS NULL AND (EXISTS ( SELECT 1
           FROM launch_prep_pair p
             JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind::text = 'площадка'::text
          WHERE p.target_id = t.id AND r.verdict IS NOT NULL AND (p.withdrawn_at IS NULL OR p.withdraw_kind::text = 'отказ в правках'::text)));

GRANT SELECT ON pub.campaign_v1 TO cabinet;
