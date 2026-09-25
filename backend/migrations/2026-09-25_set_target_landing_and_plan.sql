-- Посадочная, запрос ссылки и плановый объём — на пару «креатив × площадка»
-- (решение владельца 25.09.2026).
--
-- ЗАЧЕМ. Посадочная жила на `launch_prep_target` — паре «сделка × площадка», общей для
-- ВСЕХ креативов сделки. У разных креативов одной площадки в одной РК посадочные бывают
-- разные (разные товары), а общая запись давала «автозаполнение»: креатив №2 получал
-- посадочную креатива №1. Запрос ссылки у площадки — туда же: иначе запрос по креативу
-- №1 запирал «ок» по креативу №2, а ссылка из кабинета ложилась не в тот креатив.
--
-- Плановый объём показов задаётся аккаунтом по площадке ДЛЯ КРЕАТИВА и уходит в РК
-- как плановый: РК пересчитывает распределение с учётом заданных объёмов.
--
-- Старые поля `launch_prep_target.advertiser_url / url_requested_at / url_request_text`
-- НЕ удаляются: замораживаются, код их больше не читает (правило проекта).
--
-- Повторный накат безопасен: IF NOT EXISTS, перенос только в пустые поля,
-- ON CONFLICT DO NOTHING.

ALTER TABLE launch_prep_set_target ADD COLUMN IF NOT EXISTS advertiser_url   varchar(512);
ALTER TABLE launch_prep_set_target ADD COLUMN IF NOT EXISTS url_requested_at timestamp;
ALTER TABLE launch_prep_set_target ADD COLUMN IF NOT EXISTS url_request_text text;
ALTER TABLE launch_prep_set_target ADD COLUMN IF NOT EXISTS plan_show        integer;

COMMENT ON COLUMN launch_prep_set_target.advertiser_url IS
    'Посадочная ЭТОГО креатива на этой площадке; пусто, пока не ввёл аккаунт или не прислала площадка';
COMMENT ON COLUMN launch_prep_set_target.url_requested_at IS
    'Когда у площадки запросили посадочную для этого креатива; запрос запирает «ок» площадки';
COMMENT ON COLUMN launch_prep_set_target.url_request_text IS 'Текст запроса посадочной у площадки';
COMMENT ON COLUMN launch_prep_set_target.plan_show IS
    'Плановый объём показов площадки по этому креативу; задан — РК берёт его, остаток делит по весам';

-- Состав креатива бывает записан только парами (креативы, заведённые демо-скриптом): чтобы
-- у каждой пары было куда положить посадочную, заводим недостающие строки состава.
INSERT INTO launch_prep_set_target (set_id, target_id)
SELECT p.set_id, p.target_id FROM launch_prep_pair p
ON CONFLICT (set_id, target_id) DO NOTHING;

-- Идущие кампании не теряют уже введённое: посадочная и открытый запрос копируются во все
-- строки состава этой площадки. Только в пустые — повторный накат не затрёт новое.
UPDATE launch_prep_set_target st
   SET advertiser_url   = COALESCE(st.advertiser_url, t.advertiser_url),
       url_requested_at = COALESCE(st.url_requested_at, t.url_requested_at),
       url_request_text = COALESCE(st.url_request_text, t.url_request_text)
  FROM launch_prep_target t
 WHERE t.id = st.target_id
   AND st.advertiser_url IS NULL AND st.url_requested_at IS NULL
   AND (t.advertiser_url IS NOT NULL OR t.url_requested_at IS NOT NULL);

-- Задания кабинета площадки: посадочная и запрос — из пары «креатив × площадка».
-- Колонки и их порядок прежние, меняется только источник; барьер безопасности сохранён.
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
        AND (t.publisher_id = ANY (pub.allowed_publisher_ids()));

GRANT SELECT ON pub.task_v1 TO cabinet;
