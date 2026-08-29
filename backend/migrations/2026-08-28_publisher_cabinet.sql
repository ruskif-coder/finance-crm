-- Кабинет паблишера, слой 1: учётки и КОНТРАКТ С БАЗОЙ.
-- Состав первичных данных согласован владельцем 28.08.2026 (вариант «А» — отдельный
-- контур). Разбор решений — docs/PLAN_кабинет_паблишера.md, этапы 4–5.
--
-- Здесь три разных вещи, и путать их не стоит:
--   1. ХРАНЕНИЕ — две таблицы учёток в `public`, мастер ядро;
--   2. КОНТРАКТ — схема `pub` с view: то и только то, что кабинету видно;
--   3. ГРАНИЦА — роль `cabinet` без единой привилегии в `public`.
--
-- Изоляция строится НЕ на роли, а на контракте: роль без контракта даёт изоляцию
-- доступа и не даёт изоляции схемы, а ломать будет схема — новая таблица ядра
-- появилась бы у кабинета сама собой.

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. Учётки. Мастер — ядро: заводит и отключает их наш админ, кабинет только читает.
--
-- Учётка НА ЧЕЛОВЕКА и охватывает несколько площадок (решение владельца 23.08.2026):
-- в сетях один менеджер ведёт несколько сайтов, и учётка на площадку заставила бы его
-- держать пять паролей. Отсюда связь М:М отдельной таблицей.
CREATE TABLE IF NOT EXISTS cabinet_account (
    id              serial PRIMARY KEY,
    email           text NOT NULL UNIQUE,
    name            text NOT NULL,
    -- NULL = приглашение отправлено, пароль ещё не задан. Отличать это от «отключён»
    -- обязательно: первое ждёт человека, второе — решение админа.
    hashed_password text,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamp DEFAULT now(),
    last_login_at   timestamp
);

CREATE TABLE IF NOT EXISTS cabinet_account_publisher (
    account_id   integer NOT NULL REFERENCES cabinet_account(id) ON DELETE CASCADE,
    -- RESTRICT, а не CASCADE: площадка уходит в архив статусом, а не удалением, и
    -- случайное удаление записи реестра не должно молча отнимать доступ у человека.
    publisher_id integer NOT NULL REFERENCES sales_publishers(id) ON DELETE RESTRICT,
    added_at     timestamp DEFAULT now(),
    PRIMARY KEY (account_id, publisher_id)
);
CREATE INDEX IF NOT EXISTS ix_cabinet_acc_pub_publisher
    ON cabinet_account_publisher (publisher_id);

-- Снимок автора вердикта. Имя уже хранится (`decided_by`), почты не было: учётка на
-- человека, людей в одной сети несколько, и через год «Иванов» перестанет отличаться
-- от другого «Иванова». Снимок, а не ссылка, — по той же причине, что и у имени: смена
-- ответственного задним числом не должна переписывать историю согласований.
ALTER TABLE launch_prep_review ADD COLUMN IF NOT EXISTS decided_email text;

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. Роль кабинета.
--
-- Пароль здесь НЕ задаётся: миграция лежит в гите, а пароль — в `.env`. Роль создаётся
-- без права входа и получает его вместе с паролем отдельной командой (см. README).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cabinet') THEN
        CREATE ROLE cabinet NOLOGIN;
    END IF;
END $$;

-- ГЛАВНАЯ строка всей конструкции. Роль не имеет `USAGE` на `public` — значит таблица,
-- которую заведёт `create_all` при следующем запуске ядра, для кабинета физически
-- невидима. Не «забыли выдать грант», а «не может быть выдан».
REVOKE ALL ON SCHEMA public FROM cabinet;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cabinet;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cabinet;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM cabinet;
-- `ALTER DEFAULT PRIVILEGES` для этой роли не заводится НИКОГДА: одна такая строка
-- отменяет всю конструкцию, открывая ей каждую будущую таблицу ядра.

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. Контракт: схема `pub` и восемь будущих view (сейчас три — по слою 1).
--
-- Почему view, а не таблицы: `SELECT` отдаёт СТРОКУ ЦЕЛИКОМ, а в `sales_publishers`
-- рядом с `name`/`domain` лежит `cpm_contract` — наша закупочная цена у этой же
-- площадки, — плюс `status` переговоров, `is_exclusive`, `note`. В `sales_deals` рядом
-- с брендом — `amount`, `agency_id`, `sales_rep_id`, `brief`.
--
-- Версия в имени рабочая: расширить → переехать → сузить, чтобы ядро и кабинет
-- выкладывались независимо.
CREATE SCHEMA IF NOT EXISTS pub;
GRANT USAGE ON SCHEMA pub TO cabinet;

-- Список площадок текущей сессии. Пусто → ПУСТОЙ массив, а не «все»: забытая установка
-- обязана показывать ничего, а не всё. Это единственное место, где решается видимость
-- строк, и оно нарочно одно.
--
-- В проекте это первая функция в базе. Заведена потому, что альтернатива — повторить
-- разбор строки в каждом view, и первое же расхождение между копиями стало бы утечкой
-- между кабинетами.
CREATE OR REPLACE FUNCTION pub.allowed_publisher_ids() RETURNS integer[]
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN coalesce(current_setting('app.publisher_ids', true), '') = ''
            THEN ARRAY[]::integer[]
        ELSE string_to_array(current_setting('app.publisher_ids', true), ',')::integer[]
    END
$$;
GRANT EXECUTE ON FUNCTION pub.allowed_publisher_ids() TO cabinet;

-- Единственная запись, которую кабинет делает в `public`, — отметка времени входа.
-- Не грант на `UPDATE`, а функция: грант открыл бы таблицу целиком, включая
-- `hashed_password` и `is_active`, то есть кабинет мог бы сам себя включить обратно.
--
-- `SET search_path` у SECURITY DEFINER обязателен и является ЧАСТЬЮ защиты: без него
-- вызывающий подсовывает свою временную таблицу с именем `cabinet_account`, и функция,
-- работающая от владельца, пишет в неё. Классическая дыра, которая выглядит как
-- забытая мелочь.
CREATE OR REPLACE FUNCTION pub.touch_login(p_account_id integer) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    UPDATE cabinet_account SET last_login_at = now() WHERE id = p_account_id;
$$;
REVOKE ALL ON FUNCTION pub.touch_login(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pub.touch_login(integer) TO cabinet;

-- 3.1. Учётка — для входа. Хеш пароля кабинету нужен: он его и проверяет.
CREATE OR REPLACE VIEW pub.account_v1 AS
SELECT a.id, a.email, a.name, a.hashed_password, a.is_active
FROM cabinet_account a;

-- 3.1а. Площадки учётки. НЕ фильтруется по `app.publisher_ids` — иначе получилась бы
-- петля: кабинет читает этот список ЗАТЕМ, чтобы список установить. Фильтр здесь по
-- учётке, а её номер кабинет берёт из своего токена, а не из данных.
CREATE OR REPLACE VIEW pub.account_publisher_v1 AS
SELECT ap.account_id, ap.publisher_id, p.name, p.domain, p.code
FROM cabinet_account_publisher ap
JOIN sales_publishers p ON p.id = ap.publisher_id;

-- 3.2. Задания на согласование: пары, где площадку СПРОСИЛИ и ответа нет.
--
-- Фильтр `verdict IS NULL` не косметика: строка проверки заводится вердиктом трафика,
-- то есть в кабинет попадает ровно то, что уже прошло проверку материала. До неё
-- задания не существует, и показывать его нечем.
--
-- Что видно (владелец, 28.08.2026): бренд, рекламодатель, срок старта, услуга.
-- Чего НЕТ и не появится: сумма сделки, план показов, агентство, сейлз, бриф, наш
-- закупочный CPM, другие площадки той же сделки.
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
    r.asked_at
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

-- 3.3. Файлы креатива — для предпросмотра и скачивания.
--
-- Отдельным view, а не колонками в задании: у комплекта бывает несколько файлов, и
-- джойн размножил бы строку задания. Токен песочницы отдаётся сознательно — из него
-- собирается адрес предпросмотра, а раздача песочницы и так без авторизации: её
-- защита в том, что адрес нельзя подобрать.
CREATE OR REPLACE VIEW pub.task_file_v1 WITH (security_barrier) AS
SELECT
    p.id            AS task_id,
    f.id            AS file_id,
    f.original_name AS name,
    f.ratio         AS size,
    f.size_bytes,
    f.is_archive,
    f.sandbox_token,
    f.entry_path
FROM launch_prep_creative_file f
JOIN launch_prep_creative_set s ON s.id = f.set_id
JOIN launch_prep_pair         p ON p.set_id = s.id
JOIN launch_prep_target       t ON t.id = p.target_id
WHERE t.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.account_v1, pub.account_publisher_v1, pub.task_v1, pub.task_file_v1
    TO cabinet;

-- Ядру разрешено ПРЕВРАЩАТЬСЯ в кабинет (`SET ROLE cabinet`) — ради приборов.
-- Прав это не добавляет: у `finance_user` их и так строго больше. Зато проверка границы
-- перестаёт требовать пароля роли в тестовом контейнере, а без такой проверки главная
-- строка этой миграции (`REVOKE ALL ON SCHEMA public`) держится на честном слове.
GRANT cabinet TO finance_user;

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. Право админки в ядре заводится кодом (`app/permissions.py`), не здесь.
-- Бэкфилл ролям НЕ делается: доступ к учёткам кабинета раздаёт владелец руками.
