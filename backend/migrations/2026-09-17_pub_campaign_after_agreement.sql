-- Кампания появляется в кабинете площадки ТОЛЬКО ПОСЛЕ ЕЁ ОТВЕТА.
--
-- Правило владельца 17.09.2026. Витрина строилась на `launch_prep_target`, то есть
-- площадка видела кампанию в тот момент, когда аккаунт только завёл её в кандидаты:
-- сборка идёт, материала нет, отправки не было — а площадка уже знает, в чьих планах
-- она фигурирует. Список кандидатов меняется по десять раз, и половина из них до
-- размещения не доживает; показывать наши намерения наружу незачем.
--
-- ПОРОГ — ответ площадки по любому креативу этой пары, а не отправка ей материала.
-- Отправка это ещё вопрос; ответ — уже её работа, и прятать её от того, кто её сделал,
-- смысла нет.
--
-- ОТКАЗ ТОЖЕ СЧИТАЕТСЯ ОТВЕТОМ. Иначе строка исчезала бы из-под рук сразу после
-- нажатия «отказ», и человек решил бы, что ответ не сохранился. Она остаётся, со
-- статусом «отказ» — так витрина и рисует.
--
-- Заменяет определение из `2026-09-15_pub_campaign_view.sql` целиком: у представления
-- нет способа дописать условие, его пересоздают. Витрина, а не первичные данные —
-- согласование схемы сюда не распространяется.

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
        WHEN c.status = 'запущена'                         THEN 'в размещении'
        WHEN c.status IN ('пауза', 'остановлена')          THEN 'пауза'
        WHEN c.status = 'окончена'                         THEN 'завершён'
        WHEN coalesce(t.period_to, d.period_to) < current_date THEN 'завершён'
        -- «Согласован» у пары означает, что площадка ответила «ок»: креатив принят,
        -- остаётся дождаться флайта.
        WHEN t.state = 'согласован'                        THEN 'ждёт старта'
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
      SELECT sum(s.shows) AS shows
        FROM ad_campaign_stat s
       WHERE s.campaign_id = c.id AND s.placement_id = pl.id
  ) st ON true
  -- ЕРИД уникален для РАЗМЕЩЕНИЯ, а не для бренда: второй флайт того же бренда не должен
  -- наследовать чужой номер (требование хендоффа, и это проверенный дефект макета).
  LEFT JOIN LATERAL (
      SELECT cs.erid
        FROM launch_prep_creative_set cs
       WHERE cs.deal_id = t.deal_id AND cs.publisher_id = t.publisher_id
         AND coalesce(cs.erid, '') <> ''
       ORDER BY cs.no DESC
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
 WHERE t.publisher_id = ANY (pub.allowed_publisher_ids())
   AND t.archived_at IS NULL
   -- ПОРОГ ВИДИМОСТИ: площадка видит кампанию только после СВОЕГО ответа хотя бы по
   -- одному креативу. Отправка — ещё вопрос, а не факт; ответ — уже работа.
   AND EXISTS (
       SELECT 1
         FROM launch_prep_pair p
         JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind = 'площадка'
        WHERE p.target_id = t.id AND r.verdict IS NOT NULL
   )
   ;

GRANT SELECT ON pub.campaign_v1 TO cabinet;
