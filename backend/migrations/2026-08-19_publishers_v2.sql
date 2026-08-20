-- Паблишеры, вторая правка (2026-08-19).
--
-- 1. Договор живёт номером, а не только ссылкой в реестр.
--    При переносе рабочей таблицы из 47 упоминаний договоров пару в реестре «Договора»
--    нашли 21: там лежат договоры с клиентами, а не с площадками, и ДПД №25/08/23 —
--    один на двадцать площадок — там отсутствует вовсе. Отброшенный номер означал
--    пустой блок в карточке при заполненной колонке в исходнике. Поэтому номер
--    хранится текстом, а ссылка на реестр становится необязательной и проставляется
--    к тому же ряду, когда договор в реестре появится.
ALTER TABLE sales_publisher_contracts ALTER COLUMN contract_id DROP NOT NULL;
ALTER TABLE sales_publisher_contracts ADD COLUMN IF NOT EXISTS number_raw VARCHAR;

-- Старое UNIQUE(publisher_id, contract_id, role) не покрывает ряды без contract_id:
-- в SQL NULL не равен NULL, и один и тот же номер можно было бы добавить дважды.
CREATE UNIQUE INDEX IF NOT EXISTS uq_publisher_contract_raw
    ON sales_publisher_contracts (publisher_id, role, lower(number_raw))
    WHERE contract_id IS NULL;

-- 2. Второй мессенджер. chat_url остаётся телеграмом, MAX живёт своей ссылкой:
--    часть площадок уходит с телеграма, и период, когда работают оба, уже начался.
ALTER TABLE sales_publishers ADD COLUMN IF NOT EXISTS chat_url_max VARCHAR;

-- 3. «Есть у площадки» и «работаем с ней» — разные вещи. Наличие строки поверхности
--    отвечает на первый вопрос, флаг — на второй. Раньше это было склеено в статусе
--    интеграции, и «у них нет приложения» не отличалось от «приложение есть, но мы
--    его не продаём».
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS we_work BOOLEAN NOT NULL DEFAULT FALSE;

-- Задним числом: подключённая или готовящаяся поверхность — это работа, которая уже идёт.
UPDATE sales_publisher_surfaces
   SET we_work = TRUE
 WHERE integration_status IN ('ПОДКЛЮЧЕНО', 'СОГЛАСОВАНИЕ', 'ПРАВКИ', 'ПОДГОТОВКА')
   AND we_work IS FALSE;
