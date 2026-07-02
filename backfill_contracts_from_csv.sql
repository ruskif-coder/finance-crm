-- backfill_contracts_from_csv.sql
-- Бэкфил данных из contracts.csv (внешняя система ОРД/рекламная платформа) в таблицу contracts
-- Заполняет payment_term_days, end_date_text, cooperation_format для 19 совпавших договоров
-- Вставляет 8 новых договоров с cooperation_format из типологии: Агентство КЛ / Клиент
-- Идемпотентен: обновляет только NULL / явно устаревшие значения
-- Запускать: docker exec -i finance_db psql -U finance_user -d finance < backfill_contracts_from_csv.sql

BEGIN;

-- =====================================================================
-- 1. Добавить поля (новые данные из CSV, которых нет в нашей схеме)
--    Запустить один раз; все ADD COLUMN IF NOT EXISTS — идемпотентны
-- =====================================================================

-- Тип договора из системы ОРД (SERVICE_AGREEMENT / INTERMEDIARY_AGREEMENT)
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS doc_type varchar(50);

-- НДС применяется (true/false)
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS nds boolean;

-- Роль ПМ в договоре (EXECUTOR — исполнитель, CUSTOMER — заказчик)
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS own_legal_role varchar(20);

-- =====================================================================
-- 2. Бэкфил payment_term_days из deferralDays (CSV)
--    Обновляем только там, где сейчас NULL
-- =====================================================================

-- DB id=51  Инсайт Люди         PM-24-12-2024       CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 51 AND payment_term_days IS NULL;

-- DB id=36  Нектарин            УК-ПМ-1103          CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 36 AND payment_term_days IS NULL;

-- DB id=22  Сайтсинг            PM-01-08-23         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 22 AND payment_term_days IS NULL;

-- DB id=11  ЭмДжиКом            РМ 01-12-2023       CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 11 AND payment_term_days IS NULL;

-- DB id=21  Уайт Бокс Медиа     РМ 30-11-2023       CSV deferralDays=30 (в CSV дата: 4d20ac8b)
UPDATE contracts SET payment_term_days = 30 WHERE id = 21 AND payment_term_days IS NULL;

-- DB id=30  МегаБайт            РМ-30-08-24         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 30 AND payment_term_days IS NULL;

-- DB id=55  Безен Хелскеа РУС   PM-31-01-25         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 55 AND payment_term_days IS NULL;

-- DB id=46  Кванза Медиа Баинг  №222035             CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 46 AND payment_term_days IS NULL;

-- DB id=31  Роре Медиа          РМ-01-04-24         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 31 AND payment_term_days IS NULL;

-- DB id=54  Т-Банк              РМ-09-01-25         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 54 AND payment_term_days IS NULL;

-- DB id=57  Муви 360            РМ-10-09-25         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 57 AND payment_term_days IS NULL;

-- DB id=27  Изи-Нэт             PM-05-12-2023       CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 27 AND payment_term_days IS NULL;

-- DB id=32  Адлабс              РМ -03-06-2024      CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 32 AND payment_term_days IS NULL;

-- DB id=17  С-Маркетинг         РМ-27-12-2023       CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 17 AND payment_term_days IS NULL;

-- DB id=28  Колтач Солюшнс      PM-01/02-24         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 28 AND payment_term_days IS NULL;

-- DB id=35  Ай-Ком              РМ-11-03-24         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 35 AND payment_term_days IS NULL;

-- DB id=3   Sa Media            PM-01-06-23         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 3 AND payment_term_days IS NULL;

-- DB id=25  Орматек             PM-11-01-2024       CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 25 AND payment_term_days IS NULL;

-- DB id=20  Лазурит             PM-21-08-23         CSV deferralDays=60
UPDATE contracts SET payment_term_days = 60 WHERE id = 20 AND payment_term_days IS NULL;

-- =====================================================================
-- 3. Бэкфил end_date_text — только для строк с NULL или явно устаревших
--    (дата окончания договора из endDate CSV, обрезаем время UTC-1)
-- =====================================================================

-- id=51  Инсайт Люди    endDate 2025-12-30 → NULL в DB → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 51 AND end_date_text IS NULL;

-- id=36  Нектарин       endDate 2025-12-30 — DB уже имеет "31.12.2024" → обновить на актуальное
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 36 AND end_date_text = '31.12.2024';

-- id=22  Сайтсинг       endDate 2025-12-30 — DB "31.12.2023" → обновить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 22 AND end_date_text = '31.12.2023';

-- id=11  ЭмДжиКом       endDate 2026-12-30 — DB "31.12.2023 года" → обновить
UPDATE contracts SET end_date_text = '31.12.2026' WHERE id = 11 AND (end_date_text LIKE '%2023%' OR end_date_text IS NULL);

-- id=21  Уайт Бокс      endDate 2025-12-30 — DB NULL → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 21 AND end_date_text IS NULL;

-- id=30  МегаБайт       endDate 2025-12-30 — DB NULL → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 30 AND end_date_text IS NULL;

-- id=55  Безен Хелскеа  endDate 2025-12-30 — DB NULL → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 55 AND end_date_text IS NULL;

-- id=46  Кванза Медиа   endDate 2025-12-30 — DB "31.12.2025" → уже совпадает
-- (no update needed)

-- id=31  Роре Медиа     endDate 2025-12-30 — DB NULL → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 31 AND end_date_text IS NULL;

-- id=54  Т-Банк         endDate 2025-12-30 — DB NULL → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 54 AND end_date_text IS NULL;

-- id=57  Муви 360       endDate 2025-12-30 — DB "31.12.2025" → уже совпадает
-- (no update needed)

-- id=27  Изи-Нэт        endDate 2025-12-30 — DB длинный текст → не трогаем (бизнес-условие)

-- id=32  Адлабс         endDate 2025-12-30 — DB NULL → заполнить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 32 AND end_date_text IS NULL;

-- id=17  С-Маркетинг    endDate 2026-12-30 — DB "27.12.2024" → обновить
UPDATE contracts SET end_date_text = '31.12.2026' WHERE id = 17 AND end_date_text LIKE '%2024%';

-- id=28  Колтач Солюшнс endDate 2026-12-30 — DB "31.12.2024" → обновить
UPDATE contracts SET end_date_text = '31.12.2026' WHERE id = 28 AND end_date_text LIKE '%2024%';

-- id=35  Ай-Ком         endDate 2025-12-30 — DB длинный текст → не трогаем

-- id=3   Sa Media       endDate 2025-12-30 — DB "31.12.2023 года" → обновить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 3 AND end_date_text LIKE '%2023%';

-- id=25  Орматек        endDate 2025-12-30 — DB "31.12.2024" → обновить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 25 AND end_date_text LIKE '%2024%';

-- id=20  Лазурит        endDate 2025-12-30 — DB "31.12.2023" → обновить
UPDATE contracts SET end_date_text = '31.12.2025' WHERE id = 20 AND end_date_text LIKE '%2023%';

-- =====================================================================
-- 4. Бэкфил cooperation_format (Агентство КЛ / Клиент)
--    Маппинг: CSV type=AD_AGENCY → "Агентство КЛ", ADVERTISER → "Клиент"
--    Обновляем только там, где cooperation_format IS NULL
-- =====================================================================

-- AD_AGENCY → Агентство КЛ
-- (id=22, 30, 31, 32, 36, 46, 51, 57 уже имеют "Агентство КЛ" из исходного импорта — не трогаем)
UPDATE contracts SET cooperation_format = 'Агентство КЛ'
WHERE id IN (3, 11, 17, 21, 27, 28, 35)
  AND cooperation_format IS NULL;

-- ADVERTISER → Клиент
UPDATE contracts SET cooperation_format = 'Клиент'
WHERE id IN (20, 25, 54, 55)
  AND cooperation_format IS NULL;

-- =====================================================================
-- 5. Бэкфил doc_type, nds, own_legal_role для совпавших договоров
-- =====================================================================

UPDATE contracts SET doc_type = 'SERVICE_AGREEMENT', nds = true, own_legal_role = 'EXECUTOR'
WHERE id IN (51, 36, 22, 11, 21, 30, 55, 46, 31, 57, 27, 32, 17, 28, 35, 3, 20)
  AND doc_type IS NULL;

-- Т-Банк id=54 — SERVICE_AGREEMENT, EXECUTOR
UPDATE contracts SET doc_type = 'SERVICE_AGREEMENT', nds = true, own_legal_role = 'EXECUTOR'
WHERE id = 54 AND doc_type IS NULL;

-- Орматек id=25 — INTERMEDIARY_AGREEMENT (посреднический)
UPDATE contracts SET doc_type = 'INTERMEDIARY_AGREEMENT', nds = true, own_legal_role = 'EXECUTOR'
WHERE id = 25 AND doc_type IS NULL;

-- =====================================================================
-- 6. Вставка НОВЫХ договоров из CSV (отсутствуют в БД, не тест, не удалены)
--    counterparty_id = NULL — привязать вручную через Справочники → Договора
--    cooperation_format проставлен по типологии: AD_AGENCY→Агентство КЛ, ADVERTISER→Клиент
-- =====================================================================

-- ДД Диджитал Альянс "ДА-5/0125" (AD_AGENCY → Агентство КЛ)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('ДА-5/0125', '2025-01-14', 'ДИДЖИТАЛ АЛЬЯНС', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД МБР "РМ-01-04-25" (AD_AGENCY → Агентство КЛ; суффикс -МБР: тот же номер у РОССТ)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('РМ-01-04-25-МБР', '2024-04-01', 'МБР', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Суффикс -МБР во избежание конфликта с РОССТ. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД РОССТ "РМ-01-04-25" (AD_AGENCY → Агентство КЛ)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('РМ-01-04-25', '2024-04-01', 'РОССТ', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД Медиа Би Эйч "РМ-14-04-25" (AD_AGENCY → Агентство КЛ; own_role=CUSTOMER — мы заказчик)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('РМ-14-04-25', '2024-04-01', 'МЕДИА БИ ЭЙЧ', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'CUSTOMER',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД Хелиас Медиа "АС-АР-42" (AD_AGENCY → Агентство КЛ)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('АС-АР-42', '2024-09-02', 'ХЕЛИАС МЕДИА', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД 9 Ярдов "PM-18-12-24" (AD_AGENCY → Агентство КЛ)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('PM-18-12-24', '2024-12-18', '9 ЯРДОВ', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД Евразия "PM 30-02-2025" (AD_AGENCY → Агентство КЛ; дата: 28.02 т.к. 30.02 не существует)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('PM 30-02-2025', '2025-02-28', 'ЕВРАЗИЯ', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД DPD "306438" (AD_AGENCY → Агентство КЛ)
INSERT INTO contracts (contract_number, contract_date, counterparty_name, end_date_text,
                       payment_term_days, cooperation_format, doc_type, nds, own_legal_role, note)
VALUES ('306438', '2025-01-13', 'DPD', '31.12.2025',
        60, 'Агентство КЛ', 'SERVICE_AGREEMENT', true, 'EXECUTOR',
        'Импорт из CSV ОРД. Нужна привязка к counterparty_id.')
ON CONFLICT DO NOTHING;

-- ДД Фьюче Лаб "PM-16-11-2023"  КОНФЛИКТ: в БД id=1 тот же номер = ДИДЖИТАЛ ИНСПИРЕЙШН
-- НЕ ВСТАВЛЯЕМ автоматически — требует ручного решения (см. примечание ниже)

-- РМ 18-12-24 — подозрительная запись (имя=номер, дата мая 2026) — НЕ ВСТАВЛЯЕМ

COMMIT;

-- =====================================================================
-- ИТОГ ПОСЛЕ ВЫПОЛНЕНИЯ — проверочный запрос:
-- SELECT id, contract_number, counterparty_name, cooperation_format,
--        payment_term_days, end_date_text, doc_type, nds, own_legal_role
-- FROM contracts
-- WHERE id IN (3,11,17,20,21,22,25,27,28,30,31,32,35,36,46,51,54,55,57)
--    OR note LIKE 'Импорт из CSV ОРД%'
-- ORDER BY id;
-- =====================================================================
