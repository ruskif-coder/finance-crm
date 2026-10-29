-- Кабинет · «Кампании» (владелец 29.10.2026), две правки одной витрины:
--
-- 1. Фильтры по бренду и по рекламодателю (площадки просили). `brand` в витрине — склейка «рекламодатель · бренд»
--    для подписи строки; фильтровать по ней нельзя, поэтому обе части отдаются отдельно. Имя рекламодателя — то же,
--    что в склейке (короткое, иначе полное), чтобы фильтр и подпись совпадали.
--
-- 2. «После сверки с площадкой цифры должны фиксироваться и больше не меняться». Витрина брала показы живыми из
--    статистики, а CPM — текущий из реестра площадок: статистика досчиталась или CPM поменяли — у площадки менялись
--    цифры уже согласованного месяца. Теперь у размещения из согласованной сверки показы — его доля итога
--    (`publisher_recon_line.agreed_volume`, разнесение при согласовании), CPM — зафиксированный при согласовании
--    (`publisher_recon.cpm`). Месяц закрыт ЦЕЛИКОМ: согласованная сверка ищется по площадке и месяцу старта
--    флайта (как `reconciled` и разнесение в board._placements), и размещение без строки разнесения (отказ с нулём
--    на момент согласования, позже согласованное заново; добавленное задним числом) показывает 0 — иначе его
--    показы ложились бы поверх итога (ревью 29.10.2026). Живой факт — только у несогласованного месяца.
--
-- Новые колонки — в конце: CREATE OR REPLACE VIEW не даёт менять порядок прежних. Повторно накатываемая.

CREATE OR REPLACE VIEW pub.campaign_v1 WITH (security_barrier) AS
SELECT v.placement_id, v.publisher_id, v.site, v.brand, v.service, v.surface, v.date_from, v.date_to, v.plan,
       CASE WHEN fx.request_id IS NOT NULL THEN COALESCE(fx.agreed_volume, 0) ELSE v.fact END AS fact,
       COALESCE(fx.cpm, v.cpm) AS cpm,
       v.erid, v.status, v.reconciled,
       COALESCE(adv.short_name, adv.name)::text AS advertiser,
       NULLIF(br.name::text, '') AS brand_name
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
   -- Снятое нами (архив) площадке не показываем (правило 16.09.2026) — кроме вошедшего в согласованный итог: архив
   -- наступает и после сдачи в ОРД, и закрытый месяц не должен терять кампании (владелец 29.10.2026).
   AND (v.archived_at IS NULL OR fx.agreed_volume IS NOT NULL);
GRANT SELECT ON pub.campaign_v1 TO cabinet;
