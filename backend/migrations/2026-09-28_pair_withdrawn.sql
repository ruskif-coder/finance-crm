-- Отзыв креатива у площадки до запуска её размещения (владелец 28.09.2026).
--
-- Кто: админ или мастер аккаунтов. Когда: пока размещение площадки в РК не запущено, в
-- том числе если креатив уже выгружен в DSP. С причиной — она уходит площадке. Вернуть
-- отозванное нельзя: заново — перезагрузкой креатива по обычной процедуре (новый комплект).
--
-- Отзыв — свойство ПАРЫ «креатив × площадка», а не вердикт: вердикт пишет площадка, а
-- отзываем мы. Строка проверки площадки остаётся как была (с ответом или без) — по ней
-- видно, что успела сказать площадка до отзыва.
--
-- Повторно накатываемая: IF NOT EXISTS у колонок, CREATE OR REPLACE у представлений.

ALTER TABLE launch_prep_pair ADD COLUMN IF NOT EXISTS withdrawn_at timestamp;
ALTER TABLE launch_prep_pair ADD COLUMN IF NOT EXISTS withdrawn_by integer REFERENCES users(id);
ALTER TABLE launch_prep_pair ADD COLUMN IF NOT EXISTS withdraw_reason text;

COMMENT ON COLUMN launch_prep_pair.withdrawn_at IS
    'Когда мы отозвали креатив у площадки. NULL — не отзывали. Отозванная пара не считается ни в согласовании, ни в пороге ЕРИД, ни в объёме';
COMMENT ON COLUMN launch_prep_pair.withdrawn_by IS 'Кто отозвал';
COMMENT ON COLUMN launch_prep_pair.withdraw_reason IS 'Причина отзыва — её видит площадка';

-- Задания кабинета: отозванная пара из очереди площадки уходит.
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
        s.rights_letter_size
       FROM launch_prep_review r
         JOIN launch_prep_pair p ON p.id = r.pair_id
         JOIN launch_prep_creative_set s ON s.id = p.set_id
         JOIN launch_prep_target t ON t.id = p.target_id
         LEFT JOIN launch_prep_set_target st ON st.set_id = p.set_id AND st.target_id = p.target_id
         JOIN sales_publishers pb ON pb.id = t.publisher_id
         JOIN sales_deals d ON d.id = s.deal_id
         LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
         LEFT JOIN sales_brands br ON br.id = d.brand_id
      WHERE r.kind::text = 'площадка'::text
        AND r.verdict IS NULL
        AND p.withdrawn_at IS NULL
        AND (t.publisher_id = ANY (pub.allowed_publisher_ids()));

GRANT SELECT ON pub.task_v1 TO cabinet;

-- Кампании кабинета: порог видимости — ответ площадки по НЕотозванному креативу.
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
      SELECT sum(s.shows) AS shows
        FROM ad_campaign_stat s
       WHERE s.campaign_id = c.id AND s.placement_id = pl.id
         -- Только наш счётчик (`OWN`). Замер Weborama сравнивается на дашборде
         -- трафика, в факт площадки он не входит.
         AND s.source IN ('demo', 'dsp', 'manual', 'ms')
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
         AND coalesce(cs.erid, '') <> ''
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
 WHERE t.publisher_id = ANY (pub.allowed_publisher_ids())
   AND t.archived_at IS NULL
   -- ПОРОГ ВИДИМОСТИ: площадка видит кампанию только после СВОЕГО ответа хотя бы по
   -- одному креативу. Отправка — ещё вопрос, а не факт; ответ — уже работа.
   AND EXISTS (
       SELECT 1
         FROM launch_prep_pair p
         JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind = 'площадка'
        WHERE p.target_id = t.id AND r.verdict IS NOT NULL
          AND p.withdrawn_at IS NULL
   )
   ;

GRANT SELECT ON pub.campaign_v1 TO cabinet;
