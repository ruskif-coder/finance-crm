-- Кабинет паблишера: витрины дашборда (профиль, команда, обработанное, материалы).
-- Продолжение 2026-08-28_publisher_cabinet.sql и _verdict.sql.
--
-- Все четыре — ЧТЕНИЕ и только оно. Денег здесь по-прежнему нет: контракт их не несёт,
-- и прибор `test_no_money_words_in_the_contract` это стережёт. Кампании и суммы на
-- экране пока статика (владелец 28.08.2026: «пока ниоткуда, подними статику для
-- визуала») — она живёт на фронте, отдельным файлом, и в контракт не просачивается.

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. Профиль площадки в шапке кабинета.
--
-- Отдельно от `account_publisher_v1`: та отвечает на вопрос «что мне видно» и потому
-- фильтруется областью; эта — «кто я», и её читают по конкретному номеру площадки,
-- который кабинет уже получил из области. Смешать их значило бы отдать профиль чужой
-- площадки тому, кто угадал номер.
-- ПОВТОРНЫЙ НАКАТ (правка 31.08.2026). Представление ниже позже расширяется другой
-- миграцией, а `CREATE OR REPLACE VIEW` не умеет менять состав колонок — на втором
-- проходе он падал с `cannot drop columns from view`. Поэтому пересоздаём: зависимостей
-- между представлениями `pub` нет, DROP ничего не тянет за собой, грант выдаётся тут же.
DROP VIEW IF EXISTS pub.profile_v1;
CREATE VIEW pub.profile_v1 WITH (security_barrier) AS
SELECT p.id            AS publisher_id,
       p.name,
       p.domain,
       p.kind,
       p.network,
       -- Рабочий чат — общий, площадка в нём состоит (владелец 28.08.2026: «только
       -- почта и рабочая группа»). Личных мессенджеров менеджеров здесь нет и не будет:
       -- один канал связи, иначе переписка размывается по личкам.
       p.chat_title,
       p.chat_url,
       p.chat_url_max,
       p.media_kit_filename,
       p.tech_requirements
FROM sales_publishers p
WHERE p.id = ANY (pub.allowed_publisher_ids());

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. Команда SIMB-AD по площадке.
--
-- Собирается из сделок, которые у этой площадки в работе: аккаунт и трафик — те, кто
-- реально её ведёт, а не общий список. Телефонов нет НИГДЕ в системе (у `sales_reps` и
-- `users` таких полей не существует), и заводить их владелец не просил — отдаём почту.
--
-- Роль «документы и оплаты» в системе отсутствует: у сделки два ответственных, не три.
-- Придумывать третьего из имеющихся значило бы отправить площадку с вопросом по акту к
-- человеку, который его не видел.
-- ПОВТОРНЫЙ НАКАТ (правка 31.08.2026). Представление ниже позже расширяется другой
-- миграцией, а `CREATE OR REPLACE VIEW` не умеет менять состав колонок — на втором
-- проходе он падал с `cannot drop columns from view`. Поэтому пересоздаём: зависимостей
-- между представлениями `pub` нет, DROP ничего не тянет за собой, грант выдаётся тут же.
DROP VIEW IF EXISTS pub.team_v1;
CREATE VIEW pub.team_v1 WITH (security_barrier) AS
SELECT DISTINCT
       t.publisher_id,
       r.id                        AS rep_id,
       r.name,
       v.role,
       u.email
FROM launch_prep_target t
JOIN sales_deals d ON d.id = t.deal_id
CROSS JOIN LATERAL (VALUES ('аккаунт', d.account_manager_id),
                           ('трафик и креативы', d.traffic_manager_id)) AS v(role, rep_id)
JOIN sales_reps r ON r.id = v.rep_id
LEFT JOIN users u ON u.id = r.user_id
WHERE t.publisher_id = ANY (pub.allowed_publisher_ids());

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. Обработанное — решённые запросы.
--
-- Нужно затем, чтобы решённое УХОДИЛО из очереди, но не пропадало: «мы же ответили»
-- без места, где это видно, превращается в переписку. Комментарий отдаётся целиком —
-- в блоке под ним достаточно места, и обрезанная причина доработки бесполезна.
CREATE OR REPLACE VIEW pub.done_v1 WITH (security_barrier) AS
SELECT p.id                                   AS task_id,
       t.publisher_id,
       s.no                                   AS creative_no,
       s.title                                AS creative_title,
       coalesce(adv.short_name, adv.name)     AS advertiser,
       br.name                                AS brand,
       d.product                              AS service,
       r.verdict,
       r.reason,
       r.decided_at,
       r.decided_by,
       r.source
FROM launch_prep_review r
JOIN launch_prep_pair       p  ON p.id = r.pair_id
JOIN launch_prep_creative_set s ON s.id = p.set_id
JOIN launch_prep_target     t  ON t.id = p.target_id
JOIN sales_deals            d  ON d.id = s.deal_id
LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
LEFT JOIN sales_brands      br  ON br.id = d.brand_id
WHERE r.kind = 'площадка'
  AND r.verdict IS NOT NULL
  AND t.publisher_id = ANY (pub.allowed_publisher_ids());

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. Материалы площадки: её собственные документы.
--
-- Актов и УПД в системе НЕТ — таблиц под них не существует. Экран покажет их отдельно и
-- честно, как «появятся после сверки»; выдумывать их из документов площадки нельзя:
-- медиакит и акт отвечают на разные вопросы, и подмена одного другим — это ложь в
-- строке, которую площадка воспримет как факт.
CREATE OR REPLACE VIEW pub.document_v1 WITH (security_barrier) AS
SELECT dd.id, dd.publisher_id, dd.doc_type, dd.filename, dd.note, dd.uploaded_at
FROM sales_publisher_documents dd
WHERE dd.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.profile_v1, pub.team_v1, pub.done_v1, pub.document_v1 TO cabinet;
GRANT SELECT ON pub.profile_v1 TO cabinet;
GRANT SELECT ON pub.team_v1 TO cabinet;
