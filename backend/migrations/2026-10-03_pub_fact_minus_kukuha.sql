-- Кабинет площадки, 03.10.2026 (владелец): факт площадки — ЗА ВЫЧЕТОМ «кукухи».
--
-- «Кукуха» — блок по умолчанию площадки в нашей DSP (`dsp_block_stat`, сутки по блоку из
-- админки DSP). По кампаниям DSP его не делит, поэтому доля размещения считается по его
-- суточным показам DSP на площадке — то же правило, что у страницы «Трафики → Статистика»
-- (`app/traffic/stats.py`; прибор `test_cabinet_fact_minus_kukuha` сверяет их числами):
--
--   кукуха(размещение, день) = min(DSP размещения за день,
--                                  кукуха площадки за день × DSP размещения / DSP всех РК площадки)
--
-- Adfox «кукухи» не содержит — его показы идут в факт целиком. Факт системы не меняется:
-- вычет только здесь, в том, что видит площадка.
--
-- Определение — из 2026-10-02_pub_fact_adfox.sql, изменён только расчёт `st`.

-- 4. Кампании кабинета: отказанное в правках не прячется, статус «отказ», если живых
-- пар у площадки не осталось. Остальное — как в 2026-09-28_pair_withdrawn.sql.
CREATE OR REPLACE VIEW pub.campaign_v1 WITH (security_barrier) AS
SELECT
    t.id                                   AS placement_id,
    t.publisher_id,
    pb.domain                              AS site,
    -- «Рекламодатель · Бренд» одной строкой, как в макете. Имя агентства/рекламодателя
    -- берётся short_name — это наш стандарт именования, а не битриксовское `name`.
    (coalesce(adv.short_name, adv.name, '—')
     || coalesce(' · ' || nullif(br.name, ''), ''))       AS brand,
    d.product                              AS service,
    t.surface_kind                         AS surface,
    -- Срок РК: у пары он может быть свой, иначе берётся от сделки. Тот же порядок, что
    -- в `pub.task_v1` — два ответа на «когда идёт размещение» разошлись бы.
    coalesce(t.period_from, d.period_from) AS date_from,
    coalesce(t.period_to, d.period_to)     AS date_to,
    -- План показов — доля ЭТОЙ площадки в кампании, а не план всей кампании: в блоке
    -- площадка смотрит на себя.
    coalesce(pl.plan_show, 0)::bigint      AS plan,
    coalesce(st.shows, 0)::bigint          AS fact,
    -- CPM по договору с площадкой, до НДС. Живёт в её карточке; здесь только читается.
    coalesce(pb.cpm_contract, 0)::numeric  AS cpm,
    coalesce(er.erid, '')                  AS erid,
    -- ШЕСТЬ СОСТОЯНИЙ, порядок ветвей = приоритет. Отказ старше всего: он терминальный и
    -- не отменяется ни запуском, ни датами. Дальше — то, что говорит сама кампания, и
    -- только потом догадка по датам: «дата прошла» слабее, чем «мы её остановили».
    CASE
        WHEN rej.pair_id IS NOT NULL                       THEN 'отказ'
        -- Мы отказали площадке в правках по ВСЕМ её креативам (30.09.2026): живых пар
        -- не осталось, размещение из ротации исключено.
        WHEN dec.declined AND NOT dec.live                 THEN 'отказ'
        WHEN t.state = 'отказ площадки'                    THEN 'отказ'
        -- Площадка в РК сильнее самой РК: кампания может быть «запущена» целиком, а эта
        -- площадка ещё ждать запуска — площадке важно её собственное состояние.
        WHEN pl.status = 'запущен'                         THEN 'в размещении'
        WHEN pl.status = 'пауза'                           THEN 'пауза'
        WHEN pl.status = 'завершена'                       THEN 'завершён'
        WHEN c.status = 'запущена'                         THEN 'в размещении'
        WHEN c.status IN ('пауза', 'остановлена')          THEN 'пауза'
        WHEN c.status = 'окончена'                         THEN 'завершён'
        WHEN coalesce(t.period_to, d.period_to) < current_date THEN 'завершён'
        WHEN t.state IN ('завершён', 'сверка завершена', 'архив') THEN 'завершён'
        -- ВСЁ, ЧТО ПОСЛЕ СОГЛАСОВАНИЯ, площадке выглядит одинаково: она своё сделала и
        -- ждёт старта. Наши внутренние ступени («ерид получен», «заведён в DSP») наружу
        -- не детализируются — то же правило, что в TARGET_STATE_PUBLIC.
        WHEN t.state IN ('согласован', 'ерид получен', 'заведён в DSP', 'в размещении')
                                                           THEN 'ждёт старта'
        ELSE 'ждёт согласования'
    END                                    AS status,
    -- ПРОШЛО ЛИ РАЗМЕЩЕНИЕ СВЕРКУ ЗА ПЕРИОД. Признак, а НЕ фильтр (15.09.2026): читателей
    -- у витрины стало двое и им нужно противоположное. Блок «Актуальные кампании» на
    -- дашборде показывает только несверенное — размещение висит там до сверки; экран
    -- «Кампании» показывает ВСЁ, включая закрытые периоды.
    --
    -- Два представления с почти одинаковым SQL разошлись бы на первой же правке, и
    -- разошлись бы молча: строка перестала бы появляться на одном экране и осталась на
    -- другом. Поэтому определение одно, а отбор — у того, кто читает.
    --
    -- Самой процедуры сверки ещё нет (будет отдельно), но место готово и не пустым
    -- флагом: `publisher_request` с `kind='сверка'` уже существует, у неё есть период,
    -- вердикт и дата решения. Замер 15.09.2026: ноль строк, признак у всех false.
    EXISTS (
        SELECT 1
          FROM publisher_request pr
         WHERE pr.kind = 'сверка'
           AND pr.verdict IS NOT NULL
           AND pr.publisher_id = t.publisher_id
           -- Сверка бывает по одной сделке и за период целиком. Пустой `deal_id` —
           -- «за период»: тогда закрыты все размещения этого месяца, а не одно.
           AND (pr.deal_id IS NULL OR pr.deal_id = t.deal_id)
           -- Период сверки сопоставляется с МЕСЯЦЕМ ФЛАЙТА — из того же поля, из которого
           -- его считает экран. Второе определение периода означало бы, что строка
           -- показана в одном месяце, а закрывается другим.
           AND pr.period = to_char(coalesce(t.period_from, d.period_from), 'YYYY-MM')
    )                                      AS reconciled
  FROM launch_prep_target t
  JOIN sales_publishers pb ON pb.id = t.publisher_id
  JOIN sales_deals d       ON d.id = t.deal_id
  LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
  LEFT JOIN sales_brands br       ON br.id = d.brand_id
  -- Кампания у сделки одна (уникальный ключ по `deal_id`), поэтому join прямой.
  LEFT JOIN ad_campaign c  ON c.deal_id = d.id
  LEFT JOIN ad_campaign_placement pl
         ON pl.campaign_id = c.id AND pl.publisher_id = t.publisher_id
  -- Факт считается ПО СВОЕЙ строке размещения. Без привязки к `placement_id` площадка
  -- увидела бы показы всей кампании, включая чужие сайты, — и своя открутка выглядела бы
  -- кратно больше настоящей.
  LEFT JOIN LATERAL (
      SELECT sum(dd.own) - round(coalesce(sum(
                 CASE WHEN tt.tot > 0 AND kb.k > 0
                      THEN least(dd.dsp, kb.k::numeric * dd.dsp / tt.tot) ELSE 0 END), 0)) AS shows
        FROM (
            SELECT s.date,
                   sum(s.shows) AS own,
                   coalesce(sum(s.shows) FILTER (WHERE s.source <> 'adfox'), 0) AS dsp
              FROM ad_campaign_stat s
             WHERE s.campaign_id = c.id AND s.placement_id = pl.id
               -- Только наш счётчик (`OWN`), с 02.10.2026 — и отчёт Adfox. Замер Weborama
               -- сравнивается на дашборде трафика, в факт площадки он не входит.
               AND s.source IN ('adfox', 'demo', 'dsp', 'manual', 'ms')
             GROUP BY s.date
        ) dd
        LEFT JOIN LATERAL (
            SELECT sum(b.shows) AS k FROM dsp_block_stat b
             WHERE b.publisher_id = t.publisher_id AND b.date = dd.date
        ) kb ON true
        LEFT JOIN LATERAL (
            -- Знаменатель — показы DSP ВСЕХ РК площадки за день, не только этой.
            SELECT sum(s2.shows) AS tot
              FROM ad_campaign_stat s2
              JOIN ad_campaign_placement p2 ON p2.id = s2.placement_id
             WHERE p2.publisher_id = t.publisher_id AND s2.date = dd.date
               AND s2.source IN ('demo', 'dsp', 'manual', 'ms')
        ) tt ON true
  ) st ON true
  -- ЕРИД уникален для РАЗМЕЩЕНИЯ, а не для бренда: второй флайт того же бренда не должен
  -- наследовать чужой номер (требование хендоффа, и это проверенный дефект макета).
  -- Комплект принадлежит СДЕЛКЕ, а с площадкой его связывает ПАРА: `cs.publisher_id`
  -- у живых комплектов NULL, и старое условие не находило ничего никогда. Пара имеет
  -- приоритет, прямая привязка к площадке оставлена запасным путём.
  LEFT JOIN LATERAL (
      SELECT cs.erid
        FROM launch_prep_creative_set cs
        LEFT JOIN launch_prep_pair p2 ON p2.set_id = cs.id AND p2.target_id = t.id
       WHERE cs.deal_id = t.deal_id
         -- Только ГОТОВЫЙ маркер (`app.ord.readiness`): наш — Active/Registering, чужой — сразу.
         AND coalesce(trim(cs.erid), '') <> ''
         AND (coalesce(cs.erid_source, 'наш') <> 'наш' OR cs.ord_status IN ('Active', 'Registering'))
         AND (p2.id IS NOT NULL OR cs.publisher_id = t.publisher_id)
       ORDER BY (p2.id IS NOT NULL) DESC, cs.no DESC
       LIMIT 1
  ) er ON true
  -- Отказ площадки по любому комплекту этой пары. Одного достаточно: размещение не
  -- состоялось, и остальные вердикты этого уже не меняют.
  LEFT JOIN LATERAL (
      SELECT p.id AS pair_id
        FROM launch_prep_pair p
        JOIN launch_prep_review r ON r.pair_id = p.id
       WHERE p.target_id = t.id AND r.verdict = 'отказ'
       LIMIT 1
  ) rej ON true
  -- Отказ в правках (30.09.2026): есть ли пары, снятые НАМИ с видом «отказ в правках»,
  -- и остались ли живые — ОТПРАВЛЕННЫЕ площадке и не снятые — пары у этого получателя.
  -- Неотправленная (у трафика) площадке не видна и живой её не делает (ревью 30.09).
  LEFT JOIN LATERAL (
      SELECT bool_or(p.withdraw_kind = 'отказ в правках')              AS declined,
             bool_or(p.withdrawn_at IS NULL AND p.sent_at IS NOT NULL) AS live
        FROM launch_prep_pair p WHERE p.target_id = t.id
  ) dec ON true
 WHERE t.publisher_id = ANY (pub.allowed_publisher_ids())
   AND t.archived_at IS NULL
   -- ПОРОГ ВИДИМОСТИ: площадка видит кампанию только после СВОЕГО ответа хотя бы по
   -- одному креативу. Отправка — ещё вопрос, а не факт; ответ — уже работа.
   AND EXISTS (
       SELECT 1
         FROM launch_prep_pair p
         JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind = 'площадка'
        WHERE p.target_id = t.id AND r.verdict IS NOT NULL
          -- Отказанная в правках пара остаётся видимой (висит до сверки месяца);
          -- обычный отзыв — как раньше, скрыт.
          AND (p.withdrawn_at IS NULL OR p.withdraw_kind = 'отказ в правках')
   )
   ;

GRANT SELECT ON pub.campaign_v1 TO cabinet;
