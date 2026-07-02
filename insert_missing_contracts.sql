-- insert_missing_contracts.sql
-- Sozdayot pustyye zapisi v contracts dlya 68 kontragentov bez dogovora.
-- NOT EXISTS zaschischayet ot dubley. Idet v counterparties po INN (ili po imeni).
-- Zapuskat posle backup.

BEGIN;

-- ДПД МЕДИА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9701257829'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МБР ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7743237860'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МЕДИАНА БИ ЭЙЧ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7701906766'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АПР ЕВРАЗИЯ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7708547932'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ДИДЖИТАЛ АЛЬЯНС АО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7731276913'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ФЬЮЧЕ ЛАБ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7706426788'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ИНСТАМАРТ СЕРВИС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9705118142'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ПУГАЧЕВ ДЕНИС ДМИТРИЕВИЧ ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '771870678806'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- СЛ МЕДИА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7715018344'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Юматов Михаил Алексеевич ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '526228481122'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- КБП ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9725063452'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЭМЭМЭС КОММЬЮНИКЕЙШНЗ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7714328921'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- СЕМЕЙНАЯ АПТЕКА АПРЕЛЬ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '2309137766'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МЕДИАСКАУТ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9725079621'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- РИГЛА (НН) ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE name ILIKE 'РИГЛА (НН) ООО'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- УПРАВЛЯЮЩАЯ КОМПАНИЯ НКС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7714707736'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Юдина Елена Александровна ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '370254230177'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ХАЙЛОАД ЛАБС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9731042669'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ХЕАЛС МЕДИА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7707408358'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МАЙЛСТОУН ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7718873967'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Баранов Андрей Михайлович ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '504223479268'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- 9 ЯРДОВ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9707034314'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Новиков Ярослав Анатольевич ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '771871313660'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МЕДЭКСПОРТ-СЕВЕРНАЯ ЗВЕЗДА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '5404356555'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ПРЕМЬЕР НУТРИШИНАЛ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7728716402'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЯНДЕКС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7736207543'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АЛЬФАРМ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7733727061'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- НИЖЕГОРОДСКАЯ АПТЕЧНАЯ СЕТЬ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '5260408672'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Р-КОНФ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9701165423'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- СИ ЭС СИ ЛТД ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7706811620'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МЕДИАПУЛ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7729591450'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АРТИКС ИС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7723828649'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- А.А.И ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7704558179'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АКВАРЕЛЬ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7723913333'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- РА СА МЕДИА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7710899410'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АСТРАЗЕНЕКА ФАРМАСЬЮТИКАЛЗ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7704579700'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЯСНЫЙ СВЕТ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7727453648'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- БОЛЬШЕВИК ХОЛЛ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9705151781'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- РА АДВИЗОР ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7714412348'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ИНТЕРПУЛ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7729578280'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Лысенко Владимир Леонидович ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '773720311979'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ВЕСТ КОЛЛ ЛТД ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7702388235'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- РС ХЕЛС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7705989690'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Тадевосян Гарик Алексеевич ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '504405497952'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- СДЭК-ГЛОБАЛ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7722327689'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЖМАКИНА ОЛЬГА АНДРЕЕВНА ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '502714480381'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- НЕНАШЕВ ДЕНИС АЛЕКСАНДРОВИЧ ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '773381236989'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Руна АО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7702194399'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ТАЙМПЭД ЛТД ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7726703662'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЗДРАВСЕРВИС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7106040119'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- 1С-Битрикс ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7717586110'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- БИОНИКА МЕДИА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7726751049'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- 1-Й НОСОРОГ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7714739544'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АйПи веб-сервисы ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9731055033'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- КАСА ПИКАССА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9701301563'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АВИАСЕЙЛС БИЗНЕС ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9710080462'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МЕСТО ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9725193677'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ПРОФБУХ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7719788175'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- АГЕНТИКА ТРЕВЭЛ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7703403951'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- Бойко Сергей Владимирович ИП
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '672214229716'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ВК ЦИФРОВЫЕ ТЕХНОЛОГИИ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7714415613'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- БЕЙДЖ-ОНЛАЙН ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '5038121902'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МАНГО ТЕЛЕКОМ ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7709501144'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ПФ СКБ КОНТУР АО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '6663003127'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- НПЦ АВТОМАТИЗАЦИЯ БИЗНЕСА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7723808057'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЛИНИЯ КОНСУЛЬТАЦИЙ РУНА ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7727234950'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- ЮЭМДЖИ ГРУПП ООО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '9724057015'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

-- МЕГАФОН ПАО
INSERT INTO contracts (counterparty_id, counterparty_name, inn, note)
SELECT id, name, inn, 'Требует заполнения'
FROM counterparties
WHERE inn = '7812014560'
  AND NOT EXISTS (
      SELECT 1 FROM contracts c WHERE c.counterparty_id = counterparties.id
  )
LIMIT 1;

COMMIT;

-- Proverka: skolko dobavleno
SELECT COUNT(*) AS vsego_dogovorov FROM contracts;
SELECT COUNT(*) AS s_pometkoj FROM contracts WHERE note = 'Требует заполнения';