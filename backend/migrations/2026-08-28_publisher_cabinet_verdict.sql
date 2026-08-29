-- Кабинет паблишера, слой 2: вердикт наружу и запрос посадочной ссылки.
-- Продолжение 2026-08-28_publisher_cabinet.sql.
--
-- ГЛАВНОЕ РЕШЕНИЕ ЭТОГО СЛОЯ — в базе его не видно, поэтому записано здесь.
--
-- Кабинет НЕ ПИШЕТ в базу вовсе. Ни `cab.verdict`, ни грантов на `launch_prep_review`:
-- он вызывает ядро по внутренней сети с сервисным секретом, и вердикт записывает та же
-- функция, что записывает его со слов аккаунта.
--
-- Почему не так, как было в наброске 23.08 (схема `cab`, мастер — кабинет): правила
-- вердикта нетривиальны — неизменяемость, обязательная причина, выдача кода пары по
-- схождению, перевод получателя в «отказ площадки», порог ЕРИД. Отдельный мастер записи
-- означал бы вторую реализацию этих правил (в SQL или в сервисе кабинета) плюс перенос
-- строк между схемами. Две реализации одного правила расходятся — это в проекте уже
-- случалось со срочностью и с кварталами.
--
-- Инвариант «у таблицы один писатель» при этом не нарушен, а усилен: в
-- `launch_prep_review` пишет ТОЛЬКО ядро. Кабинет остаётся read-only в базе, и его роль
-- по-прежнему не имеет ни одной привилегии в `public`.

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. Задание обрастает тем, что нужно для действия.
--
-- `target_id` — по нему ядро понимает, чью посадочную страницу присылают: она живёт на
-- получателе (сделка × площадка), а не на креативе, и одна на все креативы кампании.
--
-- Состояние ссылки НЕ вычисляется здесь. Три ответа на «где ссылка» («не спрашивали» /
-- «ждём» / «есть») уже выведены в ядре (`url_state`), и вторая копия правила в SQL
-- разошлась бы с первой. Отдаём факты, вывод делает тот, кто рисует.
CREATE OR REPLACE VIEW pub.task_v1 WITH (security_barrier) AS
SELECT
    p.id                                    AS task_id,
    t.publisher_id,
    pb.name                                 AS publisher_name,
    pb.domain                               AS publisher_domain,
    pb.tech_requirements,
    s.id                                    AS creative_id,
    s.no                                    AS creative_no,
    s.title                                 AS creative_title,
    s.form,
    coalesce(adv.short_name, adv.name)      AS advertiser,
    br.name                                 AS brand,
    d.product                               AS service,
    coalesce(t.period_from, d.period_from)  AS period_from,
    coalesce(t.period_to,   d.period_to)    AS period_to,
    t.advertiser_url,
    r.asked_at,
    t.id                                    AS target_id,
    t.url_requested_at,
    t.url_request_text
FROM launch_prep_review r
JOIN launch_prep_pair       p  ON p.id = r.pair_id
JOIN launch_prep_creative_set s ON s.id = p.set_id
JOIN launch_prep_target     t  ON t.id = p.target_id
JOIN sales_publishers       pb ON pb.id = t.publisher_id
JOIN sales_deals            d  ON d.id = s.deal_id
LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
LEFT JOIN sales_brands      br  ON br.id = d.brand_id
WHERE r.kind = 'площадка'
  AND r.verdict IS NULL
  AND t.publisher_id = ANY (pub.allowed_publisher_ids());

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. Причины отрицательных исходов — готовые формулировки.
--
-- Два списка в одном view с признаком `kind`, а не два view: экран показывает их в
-- одном месте и переключает по выбранной кнопке. Сами списки остаются РАЗНЫМИ:
-- «товара нет в наличии» закрывает площадку для кампании, «тяжёлый файл» просит новую
-- версию — в общем списке человек выбирал бы из смеси несравнимого.
--
-- Область видимости здесь не нужна: это справочник формулировок, а не данные площадки.
CREATE OR REPLACE VIEW pub.reason_v1 AS
SELECT 'отказ'::text AS kind, id, text AS name, sort_order
FROM sales_refusal_reasons WHERE is_active
UNION ALL
SELECT 'на доработку'::text, id, name, sort_order
FROM sales_rework_reasons WHERE is_active;

GRANT SELECT ON pub.reason_v1 TO cabinet;
