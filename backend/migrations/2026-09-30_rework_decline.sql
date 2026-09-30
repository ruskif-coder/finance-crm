-- Отказ площадке в правках (владелец 30.09.2026).
--
-- Площадка прислала «на доработку», рекламодатель правки не принял: аккаунт отвечает
-- «отказать площадке в правках» с текстом. Креатив исключается из ротации РК тем же путём,
-- что отзыв (app/launch_prep/withdraw.py), а у площадки остаётся виден со статусом
-- «отказ» и подсказкой-ответом — до сверки месяца, как остальные кампании.
--
-- Повторный накат ничего не меняет.

-- 1. Вид снятия пары. Текст ответа — в уже существующем withdraw_reason.
ALTER TABLE launch_prep_pair ADD COLUMN IF NOT EXISTS withdraw_kind varchar(24);
COMMENT ON COLUMN launch_prep_pair.withdraw_kind IS
  'Вид снятия пары: отзыв (мы отозвали креатив) | отказ в правках (правки площадки не приняты)';
UPDATE launch_prep_pair SET withdraw_kind = 'отзыв'
 WHERE withdrawn_at IS NOT NULL AND withdraw_kind IS NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_pair_withdraw_kind') THEN
    ALTER TABLE launch_prep_pair ADD CONSTRAINT ck_pair_withdraw_kind
      CHECK (withdraw_kind IS NULL OR withdraw_kind IN ('отзыв', 'отказ в правках'));
  END IF;
END $$;

-- 2. Шаблоны ответа «правки не приняты» — накопитель, как фразы запроса ссылки.
CREATE TABLE IF NOT EXISTS sales_rework_decline_phrases (
    id         serial PRIMARY KEY,
    text       text    NOT NULL UNIQUE,
    sort_order integer NOT NULL DEFAULT 0,
    is_active  boolean NOT NULL DEFAULT true
);
COMMENT ON TABLE sales_rework_decline_phrases IS
  'Готовые ответы площадке, когда её правки не приняты; набранный ответ пополняет список';
INSERT INTO sales_rework_decline_phrases (text, sort_order) VALUES
  ('Рекламодатель не согласовал правки — креатив остаётся в исходном виде', 10),
  ('Правки противоречат требованиям бренда рекламодателя', 20),
  ('Рекламодатель снимает креатив с этой площадки в текущей РК', 30)
ON CONFLICT (text) DO NOTHING;

-- 3. Креативы кампании в кабинете: отказанный в правках виден со статусом и ответом.
CREATE OR REPLACE VIEW pub.campaign_creative_v1 WITH (security_barrier) AS
SELECT p.id                    AS task_id,
       t.id                    AS placement_id,
       t.publisher_id,
       s.no                    AS creative_no,
       s.title                 AS creative_title,
       s.form,
       p.agreed_at,
       (p.withdraw_kind IS NULL
        AND t.state NOT IN ('в размещении', 'завершён', 'сверка завершена', 'архив')
        AND NOT EXISTS (
            SELECT 1 FROM ad_campaign_placement pl
              JOIN ad_campaign c ON c.id = pl.campaign_id
             WHERE c.deal_id = t.deal_id AND pl.publisher_id = t.publisher_id
               AND pl.status IN ('запущен', 'пауза', 'завершена')))  AS revocable,
       CASE WHEN p.withdraw_kind = 'отказ в правках' THEN 'отказ' ELSE 'согласован' END
                               AS status,
       CASE WHEN p.withdraw_kind = 'отказ в правках' THEN p.withdraw_reason END
                               AS decline_reason
  FROM launch_prep_review r
  JOIN launch_prep_pair p ON p.id = r.pair_id
  JOIN launch_prep_creative_set s ON s.id = p.set_id
  JOIN launch_prep_target t ON t.id = p.target_id
 WHERE r.kind = 'площадка'
   AND ((r.verdict = 'ок' AND p.withdrawn_at IS NULL)
        OR p.withdraw_kind = 'отказ в правках')
   AND t.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.campaign_creative_v1 TO cabinet;

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
