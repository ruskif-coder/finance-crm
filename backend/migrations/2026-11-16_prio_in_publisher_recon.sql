-- Приоритезация в сверке с площадкой (владелец 16.11.2026: «показы по приоритезации лягут в сверку для площадки в конце
-- месяца как РК?» → путь 1: отдельными строками). Сверка, кабинет и разаллокация строились от размещений сборки баннеров
-- (`launch_prep_target`); у приоритезации своя таблица площадок, и её показы до площадки не доходили.
--
-- 1. `publisher_recon_prio_line` — согласованный объём по площадке приоритезации. Строка сверки `publisher_recon_line`
--    ссылается внешним ключом на размещение сборки, поэтому — своя таблица той же формы.
-- 2. `publisher_prio_placement_v` — строка на площадку приоритезации в форме `publisher_placement_v`: факт — показы
--    источника `prio` по её строке РК сделки (площадка приоритезации — площадка РК, `ad/build.deal_publishers`).
--    Block SIMB не вычитается — как у Adfox: в блоке SIMB приоритезация не крутится.
-- 3. `pub.campaign_v1` — кабинет площадки видит строки приоритезации в кампаниях и в своей сверке с тем же числом;
--    новая колонка `kind` ('рк' | 'приоритезация') — в конце (CREATE OR REPLACE не меняет порядок прежних).
-- Повторно накатываемая.

CREATE TABLE IF NOT EXISTS publisher_recon_prio_line (
    request_id        INTEGER NOT NULL REFERENCES publisher_request(id) ON DELETE CASCADE,   -- сверка площадки за месяц
    prio_placement_id INTEGER NOT NULL REFERENCES prio_placements(id) ON DELETE CASCADE,     -- площадка запроса приоритезации
    our_volume        BIGINT  NOT NULL,     -- наш факт за месяц на момент согласования
    agreed_volume     BIGINT  NOT NULL,     -- доля согласованного итога площадки, разнесённая на эту строку
    PRIMARY KEY (request_id, prio_placement_id)
);

CREATE OR REPLACE VIEW publisher_prio_placement_v AS
WITH fact AS (
    SELECT s.campaign_id, s.placement_id, sum(s.shows) AS shows
      FROM ad_campaign_stat s
     -- источники нашего счётчика — тем же списком, что publisher_placement_v (прибор test_stat_sources): у строки площадки
     -- в РК приоритезации по факту только 'prio' (сбор сервиса и итог файлом), но новый источник не должен молча выпасть
     WHERE s.source IN ('adfox', 'demo', 'dsp', 'manual', 'ms', 'prio') AND s.placement_id IS NOT NULL
     GROUP BY s.campaign_id, s.placement_id
)
SELECT pp.id AS placement_id,
       pp.publisher_id,
       pb.domain AS site,
       COALESCE(adv.short_name, adv.name, '—')::text || COALESCE(' · ' || NULLIF(br.name::text, ''), '') AS brand,
       d.product AS service,
       'web'::varchar(8) AS surface,      -- крутится на веб-версии аптеки (prio_site_id = ID веба площадки)
       COALESCE(r.date_start, d.period_from) AS date_from,
       COALESCE(r.date_end, d.period_to) AS date_to,
       COALESCE(pp.goal_imp, 0)::bigint AS plan,
       COALESCE(f.shows, 0)::bigint AS fact,
       COALESCE(pb.cpm_contract, 0)::numeric AS cpm,
       COALESCE(pp.erid, '')::varchar AS erid,
       CASE
           WHEN pp.status = 'отказ' THEN 'отказ'
           WHEN pp.status = 'идёт' THEN 'в размещении'
           WHEN pp.status = 'остановлено' AND pp.goal_reached_at IS NULL
                AND COALESCE(r.date_end, d.period_to) >= CURRENT_DATE THEN 'пауза'
           WHEN pp.status = 'остановлено' THEN 'завершён'
           WHEN COALESCE(r.date_end, d.period_to) < CURRENT_DATE THEN 'завершён'
           WHEN pp.status = 'согласовано' THEN 'ждёт старта'
           ELSE 'ждёт согласования'
       END AS status,
       EXISTS (SELECT 1 FROM publisher_request q
                WHERE q.kind = 'сверка' AND q.verdict IS NOT NULL AND q.publisher_id = pp.publisher_id
                  AND (q.deal_id IS NULL OR q.deal_id = r.deal_id)
                  AND q.period = to_char(COALESCE(r.date_start, d.period_from), 'YYYY-MM')) AS reconciled,
       NULL::timestamp AS archived_at,
       r.deal_id
  FROM prio_placements pp
  JOIN prio_requests r ON r.id = pp.request_id
  JOIN sales_deals d ON d.id = r.deal_id
  JOIN sales_publishers pb ON pb.id = pp.publisher_id
  LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
  LEFT JOIN sales_brands br ON br.id = d.brand_id
  LEFT JOIN LATERAL (SELECT c.id FROM ad_campaign c WHERE c.deal_id = d.id ORDER BY c.id DESC LIMIT 1) c ON true
  LEFT JOIN ad_campaign_placement pl ON pl.campaign_id = c.id AND pl.publisher_id = pp.publisher_id
  LEFT JOIN fact f ON f.campaign_id = c.id AND f.placement_id = pl.id
 -- черновик площадке не уходил — это ещё не размещение
 WHERE pp.status <> 'черновик';

CREATE OR REPLACE VIEW pub.campaign_v1 WITH (security_barrier) AS
SELECT v.placement_id, v.publisher_id, v.site, v.brand, v.service, v.surface, v.date_from, v.date_to, v.plan,
       CASE WHEN fx.request_id IS NOT NULL THEN COALESCE(fx.agreed_volume, 0) ELSE v.fact END AS fact,
       COALESCE(fx.cpm, v.cpm) AS cpm,
       v.erid, v.status, v.reconciled,
       COALESCE(adv.short_name, adv.name)::text AS advertiser,
       NULLIF(br.name::text, '') AS brand_name,
       'рк'::text AS kind
  FROM publisher_placement_v v
  JOIN launch_prep_target t ON t.id = v.placement_id
  JOIN sales_deals d ON d.id = t.deal_id
  LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
  LEFT JOIN sales_brands br ON br.id = d.brand_id
  LEFT JOIN LATERAL (SELECT q.id AS request_id, l.agreed_volume, rc.cpm::numeric AS cpm
                       FROM publisher_request q
                       JOIN publisher_recon rc ON rc.request_id = q.id
                       LEFT JOIN publisher_recon_line l ON l.request_id = q.id AND l.target_id = v.placement_id
                      WHERE q.kind = 'сверка' AND q.verdict = 'согласовано' AND q.publisher_id = v.publisher_id
                        AND q.period = to_char(v.date_from, 'YYYY-MM')
                      ORDER BY q.id DESC
                      LIMIT 1) fx ON true
 WHERE v.publisher_id = ANY (pub.allowed_publisher_ids())
   -- Снятое нами (архив) площадке не показываем (правило 16.09.2026) — кроме вошедшего в согласованный итог (29.10.2026).
   AND (v.archived_at IS NULL OR fx.agreed_volume IS NOT NULL)
UNION ALL
-- Приоритезация (16.11.2026): та же логика фиксации согласованного месяца, доля итога — из publisher_recon_prio_line.
SELECT v.placement_id, v.publisher_id, v.site, v.brand, v.service, v.surface, v.date_from, v.date_to, v.plan,
       CASE WHEN fx.request_id IS NOT NULL THEN COALESCE(fx.agreed_volume, 0) ELSE v.fact END AS fact,
       COALESCE(fx.cpm, v.cpm) AS cpm,
       v.erid, v.status, v.reconciled,
       COALESCE(adv.short_name, adv.name)::text AS advertiser,
       NULLIF(br.name::text, '') AS brand_name,
       'приоритезация'::text AS kind
  FROM publisher_prio_placement_v v
  JOIN sales_deals d ON d.id = v.deal_id
  LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
  LEFT JOIN sales_brands br ON br.id = d.brand_id
  LEFT JOIN LATERAL (SELECT q.id AS request_id, l.agreed_volume, rc.cpm::numeric AS cpm
                       FROM publisher_request q
                       JOIN publisher_recon rc ON rc.request_id = q.id
                       LEFT JOIN publisher_recon_prio_line l ON l.request_id = q.id AND l.prio_placement_id = v.placement_id
                      WHERE q.kind = 'сверка' AND q.verdict = 'согласовано' AND q.publisher_id = v.publisher_id
                        AND q.period = to_char(v.date_from, 'YYYY-MM')
                      ORDER BY q.id DESC
                      LIMIT 1) fx ON true
 WHERE v.publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.campaign_v1 TO cabinet;
