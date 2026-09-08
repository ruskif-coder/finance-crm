-- Письмо о правах на изображения — сопроводительный документ к креативу.
--
-- Решение владельца 07.09.2026: «к креативам иногда идут сопроводительные письма о правах
-- на изображения, их надо прикреплять и показывать площадке в кабинете».
--
-- ОДНО письмо на креатив (владелец), поэтому КОЛОНКИ на комплекте, а не своя таблица:
-- таблица под гарантированно единственную запись — это лишний join в каждом запросе и
-- лишний способ завести вторую строку там, где её быть не должно.
--
-- ПОЧЕМУ НЕ В `launch_prep_creative_file`, где уже лежат файлы комплекта. Два места
-- сломались бы молча:
--
--   1. `_derive_form(files)` выводит форму креатива для ОРД ИЗ СОСТАВА ФАЙЛОВ.
--      ЗАМЕРЕНО 07.09.2026: архив побеждает, и письмо рядом с материалом форму НЕ меняет
--      (`.zip + .pdf` → BannerHtml5, `.mp4 + .pdf` → Video). Ломается краевой случай:
--      комплект БЕЗ материала с одним письмом даёт `Banner` вместо `None` — то есть
--      объявляет форму, которой не из чего взяться. В ОРД письмо не идёт вовсе.
--   2. `pub.task_file_v1` отдаёт кабинету `ratio` / `sandbox_token` / `entry_path`, и
--      предпросмотр рисует по ним баннер. Письмо приехало бы туда сломанным баннером.
--
-- Белый список расширений у письма СВОЙ и уже: pdf/doc/docx/jpg/png, без zip и html.
-- У креативов архивы разрешены ради песочницы; документ по тому же пути пускать нельзя —
-- песочница заводилась ровно для чужого исполняемого кода.
--
-- СРОК ХРАНЕНИЯ — ГОД от выхода со стадии «Отчёты в ОРД» (владелец), то есть вдвое
-- короче исходных архивов креативов. Уборщика в проекте пока нет ни одного, правило
-- записано здесь и в заметке о хранилище, чтобы не выводить его заново.

ALTER TABLE launch_prep_creative_set ADD COLUMN IF NOT EXISTS rights_letter_path VARCHAR(512);
ALTER TABLE launch_prep_creative_set ADD COLUMN IF NOT EXISTS rights_letter_name VARCHAR(255);
ALTER TABLE launch_prep_creative_set ADD COLUMN IF NOT EXISTS rights_letter_type VARCHAR(128);
ALTER TABLE launch_prep_creative_set ADD COLUMN IF NOT EXISTS rights_letter_size INTEGER;
ALTER TABLE launch_prep_creative_set ADD COLUMN IF NOT EXISTS rights_letter_at TIMESTAMP;
ALTER TABLE launch_prep_creative_set ADD COLUMN IF NOT EXISTS rights_letter_by INTEGER REFERENCES users(id);

COMMENT ON COLUMN launch_prep_creative_set.rights_letter_path IS
    'Относительный ключ от корня хранилища (creatives/rl<id>_<имя>), не абсолютный путь';
COMMENT ON COLUMN launch_prep_creative_set.rights_letter_at IS
    'Когда прикреплено. Вместе с rights_letter_by отвечает на «при каком письме согласовали»';

-- Кабинет видит письмо ровно тогда же, когда и креатив: `task_v1` отдаёт задания,
-- ждущие вердикта площадки (`verdict IS NULL`), — это и есть момент «поступил на
-- согласование» из формулировки владельца. Отдельной view и отдельного правила
-- видимости не заводим: письмо наследует доступ у креатива.
--
-- Колонки дописываются В КОНЕЦ: `CREATE OR REPLACE VIEW` не разрешает менять порядок и
-- имена существующих. Состав контракта закреплён `tests/test_cabinet_contract.py` строгим
-- сравнением — список там правится этим же изменением, иначе прибор падает.
--
-- Отдаётся ИМЯ, а не путь: путь наружу не нужен, файл доставляется через ядро под
-- авторизацией кабинета (у контейнера кабинета тома `uploads` нет вовсе).
--
-- `WITH (security_barrier)` УКАЗЫВАЕТСЯ ЯВНО. `CREATE OR REPLACE VIEW` свойство НЕ
-- сохраняет: ровно так барьер потеряли 30.08.2026 в `2026-08-30_task_surface.sql`, и
-- возвращать его пришлось отдельной миграцией `2026-08-31_pub_security_barrier.sql`.
-- Без барьера планировщик вправе выполнить дешёвую пользовательскую функцию ДО фильтра
-- по площадкам — то есть на чужих строках. Ловится прибором
-- `test_every_pub_view_is_a_security_barrier`, он же поймал это здесь.
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
        t.advertiser_url,
        r.asked_at,
        t.id AS target_id,
        t.url_requested_at,
        t.url_request_text,
        t.surface_kind,
        s.rights_letter_name,
        s.rights_letter_size
       FROM launch_prep_review r
         JOIN launch_prep_pair p ON p.id = r.pair_id
         JOIN launch_prep_creative_set s ON s.id = p.set_id
         JOIN launch_prep_target t ON t.id = p.target_id
         JOIN sales_publishers pb ON pb.id = t.publisher_id
         JOIN sales_deals d ON d.id = s.deal_id
         LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
         LEFT JOIN sales_brands br ON br.id = d.brand_id
      WHERE r.kind::text = 'площадка'::text
        AND r.verdict IS NULL
        AND (t.publisher_id = ANY (pub.allowed_publisher_ids()));

GRANT SELECT ON pub.task_v1 TO cabinet;
