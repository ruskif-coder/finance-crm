-- ================================================================
-- Импорт ФИО генеральных директоров из 1С: 33 контрагентов
-- Обновляет только если director_name IS NULL (не перезаписывает)
-- ================================================================

BEGIN;

-- ГИБРИД ООО (6829098278)
UPDATE counterparties SET director_name = 'Чеклов Дмитрий Сергеевич'
  WHERE id = 176 AND director_name IS NULL;

-- МЕДИА ПЛАТФОРМА ООО (7728437590)
UPDATE counterparties SET director_name = 'Хайновская Елена Евгеньевна'
  WHERE id = 49 AND director_name IS NULL;

-- ОРМАТЕК АО (7724890784)
UPDATE counterparties SET director_name = 'Свердлик Ольга Васильевна'
  WHERE id = 42 AND director_name IS NULL;

-- АРТИКС ИС ООО (7723828649)
UPDATE counterparties SET director_name = 'Новоселов Павел Вячеславович'
  WHERE id = 644 AND director_name IS NULL;

-- ЯНДЕКС ООО (7736207543)
UPDATE counterparties SET director_name = 'Бунина Елена Игоревна'
  WHERE id = 506 AND director_name IS NULL;

-- ВЫМПЕЛКОМ ПАО (7713076301)
UPDATE counterparties SET director_name = 'Лацанич Василь'
  WHERE id = 26 AND director_name IS NULL;

-- РА СА МЕДИА ООО (7710899410)
UPDATE counterparties SET director_name = 'Бондаренко Алексей Алексеевич'
  WHERE id = 2 AND director_name IS NULL;

-- СТРОНГ АДВЕРТАЙЗИНГ ООО (9701087285)
UPDATE counterparties SET director_name = 'Сендеров Дмитрий Владимирович'
  WHERE id = 5 AND director_name IS NULL;

-- ДИДЖИТАЛЬНЫЕ ТЕХНОЛОГИИ ООО (7720410518)
UPDATE counterparties SET director_name = 'Ульянова Ольга Владимировна'
  WHERE id = 12 AND director_name IS NULL;

-- ТДЛАЗУРИТ ООО (3917032714)
UPDATE counterparties SET director_name = 'Егоров Денис Сергеевич'
  WHERE id = 16 AND director_name IS NULL;

-- ЛАЙОН КОММЬЮНИКЕЙШНЗ ООО (7743068844)
UPDATE counterparties SET director_name = 'Белоглазов Сергей Владимирович'
  WHERE id = 24 AND director_name IS NULL;

-- ТЕЛЕМИР ООО (7701974131)
UPDATE counterparties SET director_name = 'Амурцев Алексей Александрович'
  WHERE id = 27 AND director_name IS NULL;

-- ДПД МЕДИА ООО (9701257829)
UPDATE counterparties SET director_name = 'Кряжев Дмитрий Дмитриевич'
  WHERE id = 22 AND director_name IS NULL;

-- Р-АДВ ООО (7718258802)
UPDATE counterparties SET director_name = 'Большов Александр Александрович'
  WHERE id = 43 AND director_name IS NULL;

-- ДЕЛЬТА-ПЛАН ООО (6662126172)
UPDATE counterparties SET director_name = 'Коноплев Кирилл Евгеньевич'
  WHERE id = 50 AND director_name IS NULL;

-- ДИДЖИТАЛ БУСТ ООО (7734490680)
UPDATE counterparties SET director_name = 'Фетисов Василий Юрьевич'
  WHERE id = 162 AND director_name IS NULL;

-- ЭДЛУК ООО (7802927160)
UPDATE counterparties SET director_name = 'Филимонов Олег Игорьевич'
  WHERE id = 55 AND director_name IS NULL;

-- АДЛАБС.РУ ООО (5010031832)
UPDATE counterparties SET director_name = 'Иванчина Юлия Сергеевна'
  WHERE id = 130 AND director_name IS NULL;

-- РОРЕ МЕДИА ООО (7734440400)
UPDATE counterparties SET director_name = 'Бочкарев Илья Борисович'
  WHERE id = 363 AND director_name IS NULL;

-- СКАНДИ ЛАЙН ООО (5018112138)
UPDATE counterparties SET director_name = 'Шлойда Алексей Анатольевич'
  WHERE id = 66 AND director_name IS NULL;

-- ОМД НОВУС ООО (7702409904)
UPDATE counterparties SET director_name = 'Алексенко Екатерина Олеговна'
  WHERE id = 99 AND director_name IS NULL;

-- МАЙ ПЕРФОМАНС ЭЙДЖЕНСИ ООО (9725041522)
UPDATE counterparties SET director_name = 'Сафонова Елизавета Александровна'
  WHERE id = 110 AND director_name IS NULL;

-- САЙТСИНГ ООО (7715783088)
UPDATE counterparties SET director_name = 'Дацюк Алексей Леонидович'
  WHERE id = 173 AND director_name IS NULL;

-- ХЕАЛС МЕДИА ООО (7707408358)
UPDATE counterparties SET director_name = 'Иванов Юрий Ильич'
  WHERE id = 134 AND director_name IS NULL;

-- БАУШ ХЕЛС ООО (7706782987)
UPDATE counterparties SET director_name = 'Хотько Дмитрий Семёнович'
  WHERE id = 175 AND director_name IS NULL;

-- АЙТИ-СЕРВИС ООО (7704322416)
UPDATE counterparties SET director_name = 'Федоров Александр Евгеньевич'
  WHERE id = 160 AND director_name IS NULL;

-- ИЗИ-НЭТ ООО (9718107613)
UPDATE counterparties SET director_name = 'Ярковский Максим Александрович'
  WHERE id = 171 AND director_name IS NULL;

-- АГЕНТСТВО РОКИ ООО (7713472626)
UPDATE counterparties SET director_name = 'Василюк Кирилл Валерьевич'
  WHERE id = 150 AND director_name IS NULL;

-- ПФ СКБ КОНТУР АО (6663003127)
UPDATE counterparties SET director_name = 'Филатов Евгений Юрьевич'
  WHERE id = 57 AND director_name IS NULL;

-- АКТИОН-ПРЕСС ООО (7702272022)
UPDATE counterparties SET director_name = 'Чихачев Кирилл Евгеньевич'
  WHERE id = 112 AND director_name IS NULL;

-- ПБД ООО (9705143325)
UPDATE counterparties SET director_name = 'Тотмаков Андрей Андреевич'
  WHERE id = 25 AND director_name IS NULL;

-- АДВЕРТАЙЗИНГ КОММУНИКЕЙШН ЦЕНТР ООО (4706049566)
UPDATE counterparties SET director_name = 'Барласов Антон Борисович'
  WHERE id = 118 AND director_name IS NULL;

-- ЭМЭМЭС КОММЬЮНИКЕЙШНЗ ООО (7714328921)
UPDATE counterparties SET director_name = 'Коптев Сергей Иванович'
  WHERE id = 144 AND director_name IS NULL;

-- Итого: 33 UPDATE

COMMIT;

-- Проверка:
-- SELECT id, name, inn, director_name FROM counterparties WHERE director_name IS NOT NULL ORDER BY id;