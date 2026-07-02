-- ================================================================
-- Обновление реквизитов контрагентов
-- Источники: банковская выписка + ЭДО экспорт
-- Контрагентов к обновлению: 158
-- ================================================================

BEGIN;

-- ── 1. Обновляем КПП и EDO-идентификатор в таблице counterparties ──

-- 1-Й НОСОРОГ ООО
UPDATE counterparties SET kpp = '501501001', edo_id = '2BE7843f450c76e41f4873e15d9c75ecb13'
  WHERE id = 526 AND (kpp IS NULL OR edo_id IS NULL);

-- 1С-Битрикс ООО
UPDATE counterparties SET kpp = '997750001'
  WHERE id = 1 AND (kpp IS NULL);

-- 9 ЯРДОВ ООО
UPDATE counterparties SET kpp = '770701001', edo_id = '2BEee484678331a43a184ae793347a0b738'
  WHERE id = 268 AND (kpp IS NULL OR edo_id IS NULL);

-- А.А.И ООО
UPDATE counterparties SET kpp = '771501001', edo_id = '2bebdb0bf0250ae47f6880f75a0a9107b50'
  WHERE id = 167 AND (kpp IS NULL OR edo_id IS NULL);

-- АВИАСЕЙЛС БИЗНЕС ООО
UPDATE counterparties SET kpp = '771001001', edo_id = '2BM-9710080462-771001001-202004011211292294286'
  WHERE id = 469 AND (kpp IS NULL OR edo_id IS NULL);

-- АГЕНТИКА ТРЕВЭЛ ООО
UPDATE counterparties SET kpp = '770401001', edo_id = '2BM-7703403951-770301001-201601281038399794825'
  WHERE id = 560 AND (kpp IS NULL OR edo_id IS NULL);

-- АГЕНТСТВО РОКИ ООО
UPDATE counterparties SET kpp = '772801001', edo_id = '2BA434904'
  WHERE id = 150 AND (kpp IS NULL OR edo_id IS NULL);

-- АГЕНТСТВО САПЕ ООО
UPDATE counterparties SET kpp = '774301001', edo_id = '2BM-7733320702-774301001-202107060252056220706'
  WHERE id = 120 AND (kpp IS NULL OR edo_id IS NULL);

-- АДВЕРТАЙЗИНГ КОММУНИКЕЙШН ЦЕНТР ООО
UPDATE counterparties SET kpp = '470601001', edo_id = '2BM-4706049566-470601001-202206301240421113936'
  WHERE id = 118 AND (kpp IS NULL OR edo_id IS NULL);

-- АДЛАБС.РУ ООО
UPDATE counterparties SET kpp = '501001001', edo_id = '2BM-5010031832-501001001-201406181152319688193'
  WHERE id = 130 AND (kpp IS NULL OR edo_id IS NULL);

-- АЙ-ГУРУ ООО
UPDATE counterparties SET kpp = '770101001', edo_id = '2AE368AE53F-8494-46E7-8BCC-4AFCBE93C25E'
  WHERE id = 210 AND (kpp IS NULL OR edo_id IS NULL);

-- АЙТИ СМАРТ КОМПАНИ ООО
UPDATE counterparties SET kpp = '772201001', edo_id = '2AE620ec8ca-f529-4f63-ae09-8bb4ce6721ec'
  WHERE id = 35 AND (kpp IS NULL OR edo_id IS NULL);

-- АЙТИ-СЕРВИС ООО
UPDATE counterparties SET kpp = '770401001', edo_id = '2be48a8a5322a234cf7ad9c15041295cfa3'
  WHERE id = 160 AND (kpp IS NULL OR edo_id IS NULL);

-- АКВАРЕЛЬ ООО
UPDATE counterparties SET kpp = '770101001', edo_id = '2AEEE415AAE-D4F7-450D-B13D-0763099C5841'
  WHERE id = 529 AND (kpp IS NULL OR edo_id IS NULL);

-- АКОНИТ ООО
UPDATE counterparties SET kpp = '272401001', edo_id = '2BEa8e44a613a5245e5a9239c41dfc2a104'
  WHERE id = 671 AND (kpp IS NULL OR edo_id IS NULL);

-- АЛЬФА ГАРАНТ ООО
UPDATE counterparties SET kpp = '775101001'
  WHERE id = 388 AND (kpp IS NULL);

-- АЛЬФАРМ ООО
UPDATE counterparties SET kpp = '772801001', edo_id = '2BM-7733727061-772501001-201609281039147469273'
  WHERE id = 641 AND (kpp IS NULL OR edo_id IS NULL);

-- АПР ЕВРАЗИЯ ООО
UPDATE counterparties SET kpp = '770801001', edo_id = '2BM-7708547932-770801001-201503240938578326095'
  WHERE id = 478 AND (kpp IS NULL OR edo_id IS NULL);

-- АРТ-ПАБЫ ООО
UPDATE counterparties SET kpp = '770401001', edo_id = '2BM-7734412427-773401001-201805181001395034741'
  WHERE id = 32 AND (kpp IS NULL OR edo_id IS NULL);

-- АРТИКС ИС ООО
UPDATE counterparties SET kpp = '772601001', edo_id = '2BM-7723828649-772301001-201403270745298442759'
  WHERE id = 644 AND (kpp IS NULL OR edo_id IS NULL);

-- АРТЭС ООО
UPDATE counterparties SET kpp = '310201001', edo_id = '2be758f4d2829a011e28273005056917125'
  WHERE id = 544 AND (kpp IS NULL OR edo_id IS NULL);

-- АС ГЗ ООО
UPDATE counterparties SET kpp = '246201001', edo_id = '2BM-2462059130-246201001-201808091044056926387'
  WHERE id = 592 AND (kpp IS NULL OR edo_id IS NULL);

-- АСНА ООО
UPDATE counterparties SET kpp = '771601001', edo_id = '2BE39b7c493ed4d459496254bb6c32f734b'
  WHERE id = 205 AND (kpp IS NULL OR edo_id IS NULL);

-- АСТРАЗЕНЕКА ФАРМАСЬЮТИКАЛЗ ООО
UPDATE counterparties SET kpp = '770301001', edo_id = '2BM-7704579700-771401001-201407080835400704241'
  WHERE id = 423 AND (kpp IS NULL OR edo_id IS NULL);

-- Агентство Ай-Ком ООО
UPDATE counterparties SET kpp = '770601001'
  WHERE id = 557 AND (kpp IS NULL);

-- АйПи веб-сервисы ООО
UPDATE counterparties SET kpp = '773101001'
  WHERE id = 216 AND (kpp IS NULL);

-- Аржанухин Алексей Александрович ИП
UPDATE counterparties SET edo_id = '2BM-772864625847-20190201113148163950700000000'
  WHERE id = 314 AND (edo_id IS NULL);

-- БАУШ ХЕЛС ООО
UPDATE counterparties SET kpp = '774850001', edo_id = '2BM-7706782987-2013022203542538732320000000000'
  WHERE id = 175 AND (kpp IS NULL OR edo_id IS NULL);

-- БЕЗЕН ХЕЛСКЕА РУС ООО
UPDATE counterparties SET kpp = '770301001', edo_id = '2BM-7715661354-771001001-201410010831521492548'
  WHERE id = 303 AND (kpp IS NULL OR edo_id IS NULL);

-- БЕЙДЖ-ОНЛАЙН ООО
UPDATE counterparties SET kpp = '503801001', edo_id = '2BM-5038121902-503801001-201607041014020804725'
  WHERE id = 193 AND (kpp IS NULL OR edo_id IS NULL);

-- БИОНИКА МЕДИА ООО
UPDATE counterparties SET kpp = '772801001', edo_id = '2BM-7726751049-772801001-201906201240456171853'
  WHERE id = 571 AND (kpp IS NULL OR edo_id IS NULL);

-- БОЛЬШЕВИК ХОЛЛ ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-9705151781-770501001-202202011234005255086'
  WHERE id = 192 AND (kpp IS NULL OR edo_id IS NULL);

-- БРЕНД ВОТЕР ООО
UPDATE counterparties SET kpp = '771701001', edo_id = '2AED4F1E549-5A7C-4735-9034-6DD5A9A28BD0'
  WHERE id = 372 AND (kpp IS NULL OR edo_id IS NULL);

-- Бабаянц Марк Владимирович ИП
UPDATE counterparties SET edo_id = '2BEeabff72a56154baf8f3cf93b658eb662'
  WHERE id = 466 AND (edo_id IS NULL);

-- Баранов Андрей Михайлович ИП
UPDATE counterparties SET edo_id = '2BEdb4bc0814e214125a18a54bc2aaf535a'
  WHERE id = 103 AND (edo_id IS NULL);

-- Бойко Сергей Владимирович ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ
UPDATE counterparties SET edo_id = '2BM-672214229716-20180515013525697879300000000'
  WHERE id = 511 AND (edo_id IS NULL);

-- ВАПТЕКЕ ООО
UPDATE counterparties SET kpp = '381201001', edo_id = '2BM-3849058140-384901001-201607180624312319822'
  WHERE id = 545 AND (kpp IS NULL OR edo_id IS NULL);

-- ВЕСТ КОЛЛ ЛТД ООО
UPDATE counterparties SET kpp = '771901001', edo_id = '2BM-7702388235-770201001-201508130750478958184'
  WHERE id = 346 AND (kpp IS NULL OR edo_id IS NULL);

-- ВИРТУОЗ ООО
UPDATE counterparties SET kpp = '770801001', edo_id = '2BM-7708333257-770801001-201807190427085961296'
  WHERE id = 393 AND (kpp IS NULL OR edo_id IS NULL);

-- ВК ЦИФРОВЫЕ ТЕХНОЛОГИИ ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-7714415613-771401001-201710191003071933282'
  WHERE id = 117 AND (kpp IS NULL OR edo_id IS NULL);

-- ВЫМПЕЛКОМ ПАО
UPDATE counterparties SET kpp = '997750001', edo_id = '2BM-7713076301-2012052807251168061080000000000'
  WHERE id = 26 AND (kpp IS NULL OR edo_id IS NULL);

-- Верещагин Анатолий Владимирович ИП
UPDATE counterparties SET edo_id = '2BM-772641445706-20191031072846740193600000000'
  WHERE id = 14 AND (edo_id IS NULL);

-- ГИБРИД ООО
UPDATE counterparties SET kpp = '682901001', edo_id = '2BM-6829098278-682901001-201411101135015063891'
  WHERE id = 176 AND (kpp IS NULL OR edo_id IS NULL);

-- ГОЛЬФТЕХ ООО
UPDATE counterparties SET kpp = '770801001', edo_id = '2AL-BD98BDC8-7315-48BD-98D9-63DBDE0863E7-00001'
  WHERE id = 48 AND (kpp IS NULL OR edo_id IS NULL);

-- ГРИНДЕКС РУС ООО
UPDATE counterparties SET kpp = '772601001', edo_id = '2BM-7726548343-2012052808264667502630000000000'
  WHERE id = 274 AND (kpp IS NULL OR edo_id IS NULL);

-- ГРУПФОРМЕДИА ООО
UPDATE counterparties SET kpp = '774850001', edo_id = '2BM-7731529770-770201001-201411181214204205145'
  WHERE id = 666 AND (kpp IS NULL OR edo_id IS NULL);

-- Гаврилова Аурика Владимировна ИП
UPDATE counterparties SET edo_id = '2beb01d72f98d514255bc6042928725ce52'
  WHERE id = 133 AND (edo_id IS NULL);

-- Гурбанов Эльшан Шамил Оглы ИП
UPDATE counterparties SET edo_id = '2BE084ff1ea7e4b4eceb8d89c88d118267b'
  WHERE id = 206 AND (edo_id IS NULL);

-- ДАГФАРМ+ ООО
UPDATE counterparties SET kpp = '057101001', edo_id = '2BM-0571018796-057101001-202111031026397937470'
  WHERE id = 377 AND (kpp IS NULL OR edo_id IS NULL);

-- ДЕЛЬТА-ПЛАН ООО
UPDATE counterparties SET kpp = '668501001', edo_id = '2BM-6662126172-2012052808355470302630000000000'
  WHERE id = 50 AND (kpp IS NULL OR edo_id IS NULL);

-- ДИАЛОГ СТОЛИЦА ООО
UPDATE counterparties SET kpp = '772201001', edo_id = '2be7744b5df69d24a7b857101f60adde2a1'
  WHERE id = 547 AND (kpp IS NULL OR edo_id IS NULL);

-- ДИДЖИТАЛ БУСТ ООО
UPDATE counterparties SET kpp = '773401001', edo_id = '2AEEE6460E9-9A89-4369-B4CF-25395779CF20'
  WHERE id = 162 AND (kpp IS NULL OR edo_id IS NULL);

-- ДИДЖИТАЛЬНЫЕ ТЕХНОЛОГИИ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7720410518-772001001-201804101052300814017'
  WHERE id = 12 AND (kpp IS NULL OR edo_id IS NULL);

-- ДПД МЕДИА ООО
UPDATE counterparties SET kpp = '770101001', edo_id = '2BM-9701257829-770101001-202309271248401666181'
  WHERE id = 22 AND (kpp IS NULL OR edo_id IS NULL);

-- ЖМАКИНА ОЛЬГА АНДРЕЕВНА ИП
UPDATE counterparties SET edo_id = '2BEc9eba10c29884517a0b0e34a461a1d9a'
  WHERE id = 414 AND (edo_id IS NULL);

-- ЗДРАВСЕРВИС ООО
UPDATE counterparties SET kpp = '710701001', edo_id = '2BE1eeec72a2fec11e3af9f005056917125'
  WHERE id = 207 AND (kpp IS NULL OR edo_id IS NULL);

-- ИА РИАЛВЕБ ООО
UPDATE counterparties SET kpp = '781301001', edo_id = '2BE6a3dc4d4e68e444b9573a84fe47e1a80'
  WHERE id = 660 AND (kpp IS NULL OR edo_id IS NULL);

-- ИЗИ-НЭТ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-9718107613-771801001-201809080922074951554'
  WHERE id = 171 AND (kpp IS NULL OR edo_id IS NULL);

-- ИНСАЙТ ЛЮДИ ООО
UPDATE counterparties SET kpp = '770301001', edo_id = '2BM-7707450328-770701001-202104271047046714036'
  WHERE id = 189 AND (kpp IS NULL OR edo_id IS NULL);

-- ИНСТАМАРТ СЕРВИС ООО
UPDATE counterparties SET kpp = '997750001', edo_id = '2BM-9705118142-770501001-201808140708520629143'
  WHERE id = 397 AND (kpp IS NULL OR edo_id IS NULL);

-- ИНТЕРПУЛ ООО
UPDATE counterparties SET kpp = '771801001', edo_id = '2BM-7729578280-771801001-201504020751477210015'
  WHERE id = 356 AND (kpp IS NULL OR edo_id IS NULL);

-- КАСА ПИКАССА ООО
UPDATE counterparties SET kpp = '770101001'
  WHERE id = 507 AND (kpp IS NULL);

-- КБП ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-9725063452-772501001-202202150914041002707'
  WHERE id = 456 AND (kpp IS NULL OR edo_id IS NULL);

-- КВАЗАР ЛИМИТЕД ООО
UPDATE counterparties SET kpp = '774301001', edo_id = '2BM-7743181776-774301001-202008110743230140078'
  WHERE id = 107 AND (kpp IS NULL OR edo_id IS NULL);

-- КВАНЗА МЕДИА БАИНГ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7725678036-770901001-201602110216048514256'
  WHERE id = 410 AND (kpp IS NULL OR edo_id IS NULL);

-- КОМПАНИЯ СИМПЛ ООО
UPDATE counterparties SET kpp = '771401001'
  WHERE id = 381 AND (kpp IS NULL);

-- КОПИРКА24 ООО
UPDATE counterparties SET kpp = '774301001', edo_id = '2AE6F5077DD-50A5-4AC8-9E27-69F71CAF13AA'
  WHERE id = 415 AND (kpp IS NULL OR edo_id IS NULL);

-- Каминская Дарья Николаевна ИП
UPDATE counterparties SET edo_id = '2MH811eac18ede411ef976a0242ac110003'
  WHERE id = 283 AND (edo_id IS NULL);

-- Кудрявцев Алексей Васильевич ИП
UPDATE counterparties SET edo_id = '2bea478b3d3ed064e70b33674d76a40588c'
  WHERE id = 395 AND (edo_id IS NULL);

-- ЛАЙОН КОММЬЮНИКЕЙШНЗ ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-7743068844-774301001-201502090458113110848'
  WHERE id = 24 AND (kpp IS NULL OR edo_id IS NULL);

-- ЛИНИЯ КОНСУЛЬТАЦИЙ РУНА ООО
UPDATE counterparties SET kpp = '772701001'
  WHERE id = 338 AND (kpp IS NULL);

-- Лукин Евгений Витальевич ИП
UPDATE counterparties SET edo_id = '2BM-631227336588-20230801114728705453100000000'
  WHERE id = 8 AND (edo_id IS NULL);

-- Лысенко Владимир Леонидович ИП
UPDATE counterparties SET edo_id = '2BM-773720311979-20230504122706212479700000000'
  WHERE id = 281 AND (edo_id IS NULL);

-- МАЙ ПЕРФОМАНС ЭЙДЖЕНСИ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-9725041522-772501001-202101120316519045689'
  WHERE id = 110 AND (kpp IS NULL OR edo_id IS NULL);

-- МАЙЛСТОУН ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7718873967-2013022203503995026390000000000'
  WHERE id = 583 AND (kpp IS NULL OR edo_id IS NULL);

-- МАНГО ТЕЛЕКОМ ООО
UPDATE counterparties SET kpp = '772801001', edo_id = '2BM-7709501144-2013091712071711122520000000000'
  WHERE id = 98 AND (kpp IS NULL OR edo_id IS NULL);

-- МБР ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-7743237860-774301001-201804101053135196289'
  WHERE id = 391 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕГАБАЙТ ООО
UPDATE counterparties SET kpp = '770101001', edo_id = '2BM-9717094351-771701001-202408230142083306309'
  WHERE id = 323 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕГАФОН ПАО
UPDATE counterparties SET kpp = '997750001', edo_id = '2BM-7812014560-997750001-201409230510576453562'
  WHERE id = 29 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕДИА ВЕЛЬЮ АО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7706132442-2012052808190883062630000000000'
  WHERE id = 221 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕДИА ПЛАТФОРМА ООО
UPDATE counterparties SET kpp = '773401001', edo_id = '2BM-7728437590-772801001-201808070149193984523'
  WHERE id = 49 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕДИАНА БИ ЭЙЧ ООО
UPDATE counterparties SET kpp = '773101001', edo_id = '2BM-7701906766-770901001-201505220149494738225'
  WHERE id = 439 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕДИАПУЛ ООО
UPDATE counterparties SET kpp = '771801001', edo_id = '2BM-7729591450-771801001-201404110929133445164'
  WHERE id = 581 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕДИАСКАУТ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-9725079621-772501001-202204211038200078353'
  WHERE id = 30 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕДЭКСПОРТ-СЕВЕРНАЯ ЗВЕЗДА ООО
UPDATE counterparties SET kpp = '420543002', edo_id = '2BEf01f5a36ee444a488e2be4c6471de9dd'
  WHERE id = 178 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕСТО ВСТРЕЧИ №1 ООО
UPDATE counterparties SET kpp = '772001001', edo_id = '2BEd1c5b1053a4d4c17bbbcbfdec112b528'
  WHERE id = 261 AND (kpp IS NULL OR edo_id IS NULL);

-- МЕСТО ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-9725193677-772501001-202510210735344441271'
  WHERE id = 600 AND (kpp IS NULL OR edo_id IS NULL);

-- МУВИ 360 ООО
UPDATE counterparties SET kpp = '773401001', edo_id = '2BM-7731437293-773401001-201712150839347313792'
  WHERE id = 643 AND (kpp IS NULL OR edo_id IS NULL);

-- НАИТА ООО
UPDATE counterparties SET kpp = '784301001', edo_id = '2BM-7843022307-784301001-202304051041022563739'
  WHERE id = 58 AND (kpp IS NULL OR edo_id IS NULL);

-- НЕНАШЕВ ДЕНИС АЛЕКСАНДРОВИЧ ИП
UPDATE counterparties SET edo_id = '2BM-773381236989-20190225070125283611200000000'
  WHERE id = 530 AND (edo_id IS NULL);

-- НИЖЕГОРОДСКАЯ АПТЕЧНАЯ СЕТЬ ООО
UPDATE counterparties SET kpp = '526001001', edo_id = '2BE4b1ad23a3d5b4be5b9d55bf2175aff34'
  WHERE id = 276 AND (kpp IS NULL OR edo_id IS NULL);

-- НПЦ АВТОМАТИЗАЦИЯ БИЗНЕСА ООО
UPDATE counterparties SET kpp = '770401001', edo_id = '2BM-7723808057-772301001-201511190832400756881'
  WHERE id = 258 AND (kpp IS NULL OR edo_id IS NULL);

-- ОБРАЗ ООО
UPDATE counterparties SET kpp = '272401001', edo_id = '2beaa405e9585384b40b5203a8e8130ffac'
  WHERE id = 157 AND (kpp IS NULL OR edo_id IS NULL);

-- ОМД НОВУС ООО
UPDATE counterparties SET kpp = '770201001', edo_id = '2BM-7702409904-770201001-201701180128349833591'
  WHERE id = 99 AND (kpp IS NULL OR edo_id IS NULL);

-- ОРД-А ООО
UPDATE counterparties SET kpp = '771501001', edo_id = '2BM-9715420338-771501001-202206090846065038630'
  WHERE id = 4 AND (kpp IS NULL OR edo_id IS NULL);

-- ОРМАТЕК АО
UPDATE counterparties SET kpp = '774950001', edo_id = '2BM-7724890784-2013112512183967040250000000000'
  WHERE id = 42 AND (kpp IS NULL OR edo_id IS NULL);

-- ПБД ООО
UPDATE counterparties SET kpp = '770501001', edo_id = '2BM-9705143325-770501001-202004240140316487264'
  WHERE id = 25 AND (kpp IS NULL OR edo_id IS NULL);

-- ПРЕМЬЕР НУТРИШИНАЛ ООО
UPDATE counterparties SET kpp = '773001001', edo_id = '2BM-7728716402-773001001-201412260801384272972'
  WHERE id = 249 AND (kpp IS NULL OR edo_id IS NULL);

-- ПРОФБУХ ООО
UPDATE counterparties SET kpp = '772901001'
  WHERE id = 577 AND (kpp IS NULL);

-- ПУГАЧЕВ ДЕНИС ДМИТРИЕВИЧ ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ
UPDATE counterparties SET edo_id = '2BM-771870678806-20241017112412189017600000000'
  WHERE id = 123 AND (edo_id IS NULL);

-- ПФ СКБ КОНТУР АО
UPDATE counterparties SET kpp = '997750001', edo_id = '2BM-6663003127-2012052807192968181080000000000'
  WHERE id = 57 AND (kpp IS NULL OR edo_id IS NULL);

-- Р-АДВ ООО
UPDATE counterparties SET kpp = '771801001', edo_id = '2BE611ad13d353849fbb07f9fe0d661187f'
  WHERE id = 43 AND (kpp IS NULL OR edo_id IS NULL);

-- Р-КОНФ ООО
UPDATE counterparties SET kpp = '772401001', edo_id = '2BM-9701165423-772501001-202303060953066859884'
  WHERE id = 78 AND (kpp IS NULL OR edo_id IS NULL);

-- РА АДВИЗОР ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-7714412348-771401001-201610311034148922723'
  WHERE id = 637 AND (kpp IS NULL OR edo_id IS NULL);

-- РА СА МЕДИА ООО
UPDATE counterparties SET kpp = '772301001', edo_id = '2BM-7710899410-772301001-201412040957391934539'
  WHERE id = 2 AND (kpp IS NULL OR edo_id IS NULL);

-- РИГЛА ООО
UPDATE counterparties SET kpp = '772401001', edo_id = '2BE440A7C1A609511E2BB6E005056917125'
  WHERE id = 247 AND (kpp IS NULL OR edo_id IS NULL);

-- РОРЕ МЕДИА ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-7734440400-773401001-202204271117108269464'
  WHERE id = 363 AND (kpp IS NULL OR edo_id IS NULL);

-- РОСКОМНАДЗОР
UPDATE counterparties SET kpp = '770501001'
  WHERE id = 413 AND (kpp IS NULL);

-- РПК ПЛЕЙС ПРИНТ ООО
UPDATE counterparties SET kpp = '773301001', edo_id = '2AE8500255C-D7F3-412E-86BA-B9F2047DEEF1'
  WHERE id = 97 AND (kpp IS NULL OR edo_id IS NULL);

-- РС ХЕЛС ООО
UPDATE counterparties SET kpp = '770501001', edo_id = '2BM-7705989690-772501001-201601191012298188142'
  WHERE id = 528 AND (kpp IS NULL OR edo_id IS NULL);

-- Руна АО
UPDATE counterparties SET kpp = '772701001', edo_id = '2AEfbaca0a9-9ef4-4a30-a96f-d3ba5d5465ac'
  WHERE id = 191 AND (kpp IS NULL OR edo_id IS NULL);

-- САЙТСИНГ ООО
UPDATE counterparties SET kpp = '771501001', edo_id = '2BM-7715783088-771501001-201407220937506510632'
  WHERE id = 173 AND (kpp IS NULL OR edo_id IS NULL);

-- СДЭК-ГЛОБАЛ ООО
UPDATE counterparties SET kpp = '540601001', edo_id = '2BM-7722327689-772201001-201603220528496841006'
  WHERE id = 569 AND (kpp IS NULL OR edo_id IS NULL);

-- СЕМЕЙНАЯ АПТЕКА АПРЕЛЬ ООО
UPDATE counterparties SET kpp = '230901001', edo_id = '2be73e7eb20d2b84342a8b4023ed9eebd3e'
  WHERE id = 553 AND (kpp IS NULL OR edo_id IS NULL);

-- СИ ЭС СИ ЛТД ООО
UPDATE counterparties SET kpp = '772401001', edo_id = '2BM-7706811620-770601001-201412180643474248358'
  WHERE id = 382 AND (kpp IS NULL OR edo_id IS NULL);

-- СКАНДИ ЛАЙН ООО
UPDATE counterparties SET kpp = '501801001', edo_id = '2BM-5018112138-2012052808221350342630000000000'
  WHERE id = 66 AND (kpp IS NULL OR edo_id IS NULL);

-- СКЛАД ЗДОРОВЬЯ ООО
UPDATE counterparties SET kpp = '590301001', edo_id = '2BE45836C15D3AE407089415F07C5CF4DBF'
  WHERE id = 570 AND (kpp IS NULL OR edo_id IS NULL);

-- СЛ МЕДИА ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7715018344-2012052807253278741080000000000'
  WHERE id = 608 AND (kpp IS NULL OR edo_id IS NULL);

-- СОЦИАЛЬНАЯ АПТЕКА ООО
UPDATE counterparties SET kpp = '057201001', edo_id = '2BM-0571008484-057101001-201707270700008510543'
  WHERE id = 376 AND (kpp IS NULL OR edo_id IS NULL);

-- СПРАВМЕДИКА ООО
UPDATE counterparties SET kpp = '165001001', edo_id = '2BEf173faa493e111e3b670005056917125'
  WHERE id = 591 AND (kpp IS NULL OR edo_id IS NULL);

-- СТИМУЛ ПЛЮС ООО
UPDATE counterparties SET kpp = '550301001', edo_id = '2BE0bf3bc8450414960aee6f1351c0f10fd'
  WHERE id = 482 AND (kpp IS NULL OR edo_id IS NULL);

-- СТРАТЕГИЯ ФАРМА ООО
UPDATE counterparties SET kpp = '710001001', edo_id = '2BEaf24cc77e9e4444ab1a950e5463a61b5'
  WHERE id = 484 AND (kpp IS NULL OR edo_id IS NULL);

-- СТРОЙ ФОНД ООО
UPDATE counterparties SET kpp = '352501001', edo_id = '2BE493fd5735f6f408bba1bd6531b6577a9'
  WHERE id = 616 AND (kpp IS NULL OR edo_id IS NULL);

-- СТРОНГ АДВЕРТАЙЗИНГ ООО
UPDATE counterparties SET kpp = '770101001', edo_id = '2BM-9701087285-770101001-201803290929241105230'
  WHERE id = 5 AND (kpp IS NULL OR edo_id IS NULL);

-- СУПЕРФАРМА ООО
UPDATE counterparties SET kpp = '272401001', edo_id = '2beb8f0a408e7924d1abd2c03df4cb6c908'
  WHERE id = 187 AND (kpp IS NULL OR edo_id IS NULL);

-- СФЕРА ООО
UPDATE counterparties SET kpp = '781301001', edo_id = '2BE92ecb8a27abb4210b6def30a54d45fd9'
  WHERE id = 361 AND (kpp IS NULL OR edo_id IS NULL);

-- Сарбукова Елена Владимировна ИП
UPDATE counterparties SET edo_id = '2MH50f272ecf59a11eea25e0242ac110003'
  WHERE id = 286 AND (edo_id IS NULL);

-- ТАЙМПЭД ЛТД ООО
UPDATE counterparties SET kpp = '772601001', edo_id = '2BM-7726703662-772601001-201407171008200189794'
  WHERE id = 301 AND (kpp IS NULL OR edo_id IS NULL);

-- ТАНДЕР АО
UPDATE counterparties SET kpp = '231001001', edo_id = '2BM-2310031475-2012070307370849459200000000000'
  WHERE id = 552 AND (kpp IS NULL OR edo_id IS NULL);

-- ТБАНК АО
UPDATE counterparties SET kpp = '771301001', edo_id = '2BM-7710140679-2012052808235992662630000000000'
  WHERE id = 386 AND (kpp IS NULL OR edo_id IS NULL);

-- ТДЛАЗУРИТ ООО
UPDATE counterparties SET kpp = '391701001', edo_id = '2BM-3917032714-391701001-201401201116588320406'
  WHERE id = 16 AND (kpp IS NULL OR edo_id IS NULL);

-- ТЕЛЕМИР ООО
UPDATE counterparties SET kpp = '772801001', edo_id = '2BM-7701974131-770101001-201604131047441707124'
  WHERE id = 27 AND (kpp IS NULL OR edo_id IS NULL);

-- ТОП ДИДЖИТАЛ ООО
UPDATE counterparties SET kpp = '773101001', edo_id = '2BM-7731347547-773101001-201704241144444726083'
  WHERE id = 172 AND (kpp IS NULL OR edo_id IS NULL);

-- Тадевосян Гарик Алексеевич ИП
UPDATE counterparties SET edo_id = '2AE0CB6AFEA-575D-483C-8724-99E92D0C47D8'
  WHERE id = 404 AND (edo_id IS NULL);

-- Тихонин Кирилл Юрьевич ИП
UPDATE counterparties SET edo_id = '2BM-780406741183--2015053106270803160820000000'
  WHERE id = 94 AND (edo_id IS NULL);

-- УАЙТ БОКС МЕДИА ООО
UPDATE counterparties SET kpp = '772001001', edo_id = '2BM-9731048741-773101001-201910070238075372007'
  WHERE id = 208 AND (kpp IS NULL OR edo_id IS NULL);

-- УК АС ФАРМИЯ ООО
UPDATE counterparties SET kpp = '366501001', edo_id = '2bee215d1ac816b4c81952772a949d3dcd7'
  WHERE id = 485 AND (kpp IS NULL OR edo_id IS NULL);

-- УК МАКСАВИТ ООО
UPDATE counterparties SET kpp = '526201001', edo_id = '2BE69b13b5f8a374920996ecb4ec4593840'
  WHERE id = 483 AND (kpp IS NULL OR edo_id IS NULL);

-- УПРАВЛЯЮЩАЯ КОМПАНИЯ НКС ООО
UPDATE counterparties SET kpp = '770301001', edo_id = '2BE06cea7402cc311e3ac22005056917125'
  WHERE id = 330 AND (kpp IS NULL OR edo_id IS NULL);

-- ФАРМЛЕНД АО
UPDATE counterparties SET kpp = '027701001'
  WHERE id = 282 AND (kpp IS NULL);

-- ФАРМЛИНК ООО
UPDATE counterparties SET kpp = '502401001', edo_id = '2AE3F792265-F5AD-4978-8C73-4B88B4A9120D'
  WHERE id = 177 AND (kpp IS NULL OR edo_id IS NULL);

-- ФЬЮЧЕ ЛАБ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7706426788-770601001-201510230138073276467'
  WHERE id = 185 AND (kpp IS NULL OR edo_id IS NULL);

-- ХАЙЛОАД ЛАБС ООО
UPDATE counterparties SET kpp = '344401001', edo_id = '2BM-9731042669-773101001-201907180147323154112'
  WHERE id = 161 AND (kpp IS NULL OR edo_id IS NULL);

-- ХЕАЛС МЕДИА ООО
UPDATE counterparties SET kpp = '770701001', edo_id = '2BM-7707408358-770701001-201908200143078353835'
  WHERE id = 134 AND (kpp IS NULL OR edo_id IS NULL);

-- ХЭДХАНТЕР ООО
UPDATE counterparties SET kpp = '997750001', edo_id = '2BM-7718620740-2012113009360828763240000000000'
  WHERE id = 56 AND (kpp IS NULL OR edo_id IS NULL);

-- ШОКОЛАДНАЯ КОРПОРАЦИЯ ООО
UPDATE counterparties SET kpp = '616801001', edo_id = '2BEc917295cdd094943ae49773926eca4a8'
  WHERE id = 434 AND (kpp IS NULL OR edo_id IS NULL);

-- ЭДЛУК ООО
UPDATE counterparties SET kpp = '780401001', edo_id = '2AE8C7C53D6-EE69-47F0-AF3A-E2E7DF8AC164'
  WHERE id = 55 AND (kpp IS NULL OR edo_id IS NULL);

-- ЭМДЖИКОМ ООО
UPDATE counterparties SET kpp = '772501001', edo_id = '2BM-7725560073-772501001-201409220716097123403'
  WHERE id = 36 AND (kpp IS NULL OR edo_id IS NULL);

-- ЭМЭМЭС КОММЬЮНИКЕЙШНЗ ООО
UPDATE counterparties SET kpp = '771401001', edo_id = '2BM-7714328921-771401001-201711010144207842978'
  WHERE id = 144 AND (kpp IS NULL OR edo_id IS NULL);

-- ЮЭМДЖИ ГРУПП ООО
UPDATE counterparties SET kpp = '773101001', edo_id = '2BM-9724057015-772401001-202202090811110596513'
  WHERE id = 495 AND (kpp IS NULL OR edo_id IS NULL);

-- Юматов Михаил Алексеевич ИП
UPDATE counterparties SET edo_id = '2BM-526228481122-20210729090032133146700000000'
  WHERE id = 119 AND (edo_id IS NULL);

-- ЯНДЕКС ООО
UPDATE counterparties SET kpp = '997750001', edo_id = '2BM-7736207543-2012091311282509918620000000000'
  WHERE id = 506 AND (kpp IS NULL OR edo_id IS NULL);

-- ЯСНЫЙ СВЕТ ООО
UPDATE counterparties SET kpp = '772701001', edo_id = '2BM-7727453648-772701001-202012130500350723197'
  WHERE id = 51 AND (kpp IS NULL OR edo_id IS NULL);

-- Итого UPDATE counterparties: 153 строк

-- ── 2. Добавляем банковские реквизиты в counterparty_bank_accounts ──
-- (пропускаем если р/с уже есть для этого контрагента)

-- 1-Й НОСОРОГ ООО | 40702810800000037072
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 526, '40702810800000037072', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 526 AND rs = '40702810800000037072');

-- 1С-Битрикс ООО | 40702810732170001637
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 1, '40702810732170001637', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 1 AND rs = '40702810732170001637');

-- 9 ЯРДОВ ООО | 40702810302620018340
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 268, '40702810302620018340', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 268 AND rs = '40702810302620018340');

-- А.А.И ООО | 40702810036000005923
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 167, '40702810036000005923', '044525112', 'Московский филиал АБ "РОССИЯ" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 167 AND rs = '40702810036000005923');

-- АВИАСЕЙЛС БИЗНЕС ООО | 40702810601500098512
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 469, '40702810601500098512', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 469 AND rs = '40702810601500098512');

-- АГЕНТИКА ТРЕВЭЛ ООО | 40702810910000877976
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 560, '40702810910000877976', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 560 AND rs = '40702810910000877976');

-- АГЕНТСТВО САПЕ ООО | 40702810838000356075
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 120, '40702810838000356075', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 120 AND rs = '40702810838000356075');

-- АДЛАБС.РУ ООО | 40702810287360053951
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 130, '40702810287360053951', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 130 AND rs = '40702810287360053951');

-- АДЛАБС.РУ ООО | 40702810100000163176
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 130, '40702810100000163176', '044525700', 'АО "Райффайзенбанк" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 130 AND rs = '40702810100000163176');

-- АЙТИ-СЕРВИС ООО | 40702810102830004205
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 160, '40702810102830004205', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 160 AND rs = '40702810102830004205');

-- АКВАРЕЛЬ ООО | 40702810602790005006
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 529, '40702810602790005006', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 529 AND rs = '40702810602790005006');

-- АЛЬФА ГАРАНТ ООО | 40702810300000024992
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 388, '40702810300000024992', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 388 AND rs = '40702810300000024992');

-- АЛЬФАРМ ООО | 40702810900014812074
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 641, '40702810900014812074', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 641 AND rs = '40702810900014812074');

-- АПР ЕВРАЗИЯ ООО | 40702810387360051934
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 478, '40702810387360051934', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 478 AND rs = '40702810387360051934');

-- АПР ЕВРАЗИЯ ООО | 40702810701850005449
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 478, '40702810701850005449', '044525388', 'ТКБ БАНК ПАО г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 478 AND rs = '40702810701850005449');

-- АРТИКС ИС ООО | 40702810602860006252
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 644, '40702810602860006252', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 644 AND rs = '40702810602860006252');

-- АРТЭС ООО | 40702810205250005436
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 544, '40702810205250005436', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 544 AND rs = '40702810205250005436');

-- АС ГЗ ООО | 40702810423590004290
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 592, '40702810423590004290', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 592 AND rs = '40702810423590004290');

-- АСНА ООО | 40702810138000067967
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 205, '40702810138000067967', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 205 AND rs = '40702810138000067967');

-- АСТРАЗЕНЕКА ФАРМАСЬЮТИКАЛЗ ООО | 40702810500000218197
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 423, '40702810500000218197', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 423 AND rs = '40702810500000218197');

-- Агентство Ай-Ком ООО | 40702810200000038959
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 557, '40702810200000038959', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 557 AND rs = '40702810200000038959');

-- АйПи веб-сервисы ООО | 40702810438720006490
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 216, '40702810438720006490', '040702615', 'СТАВРОПОЛЬСКОЕ ОТДЕЛЕНИЕ N5230 ПАО СБЕРБАНК г Ставрополь', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 216 AND rs = '40702810438720006490');

-- АйПи веб-сервисы ООО | 40702810200000032824
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 216, '40702810200000032824', '044525225', 'ПАО Сбербанк г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 216 AND rs = '40702810200000032824');

-- Аржанухин Алексей Александрович ИП | 40802810200000088605
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 314, '40802810200000088605', '040813608', 'ДАЛЬНЕВОСТОЧНЫЙ БАНК ПАО СБЕРБАНК г Хабаровск', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 314 AND rs = '40802810200000088605');

-- БАУШ ХЕЛС ООО | 40702810100770004427
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 175, '40702810100770004427', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 175 AND rs = '40702810100770004427');

-- БЕЙДЖ-ОНЛАЙН ООО | 40702810240000037416
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 193, '40702810240000037416', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 193 AND rs = '40702810240000037416');

-- БИОНИКА МЕДИА ООО | 40702810838000003328
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 571, '40702810838000003328', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 571 AND rs = '40702810838000003328');

-- БОЛЬШЕВИК ХОЛЛ ООО | 40702810701880001989
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 192, '40702810701880001989', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 192 AND rs = '40702810701880001989');

-- БРЕНД ВОТЕР ООО | 40702810500257701234
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 372, '40702810500257701234', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 372 AND rs = '40702810500257701234');

-- Бабаянц Марк Владимирович ИП | 40802810107850000635
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 466, '40802810107850000635', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 466 AND rs = '40802810107850000635');

-- Баранов Андрей Михайлович ИП | 40802810200000426571
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 103, '40802810200000426571', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 103 AND rs = '40802810200000426571');

-- Бойко Сергей Владимирович ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ | 40802810300000008459
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 511, '40802810300000008459', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 511 AND rs = '40802810300000008459');

-- ВАПТЕКЕ ООО | 40702810331110009527
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 545, '40702810331110009527', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 545 AND rs = '40702810331110009527');

-- ВЕСТ КОЛЛ ЛТД ООО | 40702810901100022286
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 346, '40702810901100022286', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 346 AND rs = '40702810901100022286');

-- ВИРТУОЗ ООО | 40702810602660002278
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 393, '40702810602660002278', '040349602', 'КРАСНОДАРСКОЕ ОТДЕЛЕНИЕ N8619 ПАО СБЕРБАНК г Краснодар', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 393 AND rs = '40702810602660002278');

-- ВК ЦИФРОВЫЕ ТЕХНОЛОГИИ ООО | 40702810520000166258
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 117, '40702810520000166258', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 117 AND rs = '40702810520000166258');

-- ГИБРИД ООО | 40702810610000003383
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 176, '40702810610000003383', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 176 AND rs = '40702810610000003383');

-- ГОЛЬФТЕХ ООО | 40702810610000156832
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 48, '40702810610000156832', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 48 AND rs = '40702810610000156832');

-- ГРИНДЕКС РУС ООО | 40702810000000218370
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 274, '40702810000000218370', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 274 AND rs = '40702810000000218370');

-- Гурбанов Эльшан Шамил Оглы ИП | 40802810060100017066
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 206, '40802810060100017066', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 206 AND rs = '40802810060100017066');

-- ДАГФАРМ+ ООО | 40702810060320003646
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 377, '40702810060320003646', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 377 AND rs = '40702810060320003646');

-- ДИАЛОГ СТОЛИЦА ООО | 40702810038000027803
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 547, '40702810038000027803', '044525974', 'АО "ТБанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 547 AND rs = '40702810038000027803');

-- ДИДЖИТАЛ АЛЬЯНС АО | 40702810200100000843
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 362, '40702810200100000843', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 362 AND rs = '40702810200100000843');

-- ДИДЖИТАЛ АЛЬЯНС АО | 40702810300100010843
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 362, '40702810300100010843', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 362 AND rs = '40702810300100010843');

-- ДИДЖИТАЛ БУСТ ООО | 40702810202370022032
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 162, '40702810202370022032', '044525112', 'Московский филиал АБ "РОССИЯ" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 162 AND rs = '40702810202370022032');

-- ДПД МЕДИА ООО | 40702810302860022109
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 22, '40702810302860022109', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 22 AND rs = '40702810302860022109');

-- ЖМАКИНА ОЛЬГА АНДРЕЕВНА ИП | 40802810120000857430
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 414, '40802810120000857430', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 414 AND rs = '40802810120000857430');

-- ЖМАКИНА ОЛЬГА АНДРЕЕВНА ИП | 40802810100001929520
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 414, '40802810100001929520', '044525068', 'ООО "ОЗОН Банк" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 414 AND rs = '40802810100001929520');

-- Жучкова Дарья Игоревна ИП | 40802810600004491746
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 617, '40802810600004491746', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 617 AND rs = '40802810600004491746');

-- ИА РИАЛВЕБ ООО | 40702810900000025788
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 660, '40702810900000025788', '044525545', 'АО ЮниКредит Банк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 660 AND rs = '40702810900000025788');

-- ИЗИ-НЭТ ООО | 40702810302620003559
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 171, '40702810302620003559', '044525068', 'ООО "ОЗОН Банк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 171 AND rs = '40702810302620003559');

-- ИЗИ-НЭТ ООО | 40702810925644213745
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 171, '40702810925644213745', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 171 AND rs = '40702810925644213745');

-- ИНСАЙТ ЛЮДИ ООО | 40702810800000157772
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 189, '40702810800000157772', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 189 AND rs = '40702810800000157772');

-- ИНСТАМАРТ СЕРВИС ООО | 40702810538000250727
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 397, '40702810538000250727', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 397 AND rs = '40702810538000250727');

-- ИНТЕРПУЛ ООО | 40702810138000019591
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 356, '40702810138000019591', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 356 AND rs = '40702810138000019591');

-- КАСА ПИКАССА ООО | 40702810710001723669
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 507, '40702810710001723669', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 507 AND rs = '40702810710001723669');

-- КБП ООО | 40702810012010137198
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 456, '40702810012010137198', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 456 AND rs = '40702810012010137198');

-- КБП ООО | 40702810501300030562
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 456, '40702810501300030562', '044525225', 'ПАО Сбербанк г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 456 AND rs = '40702810501300030562');

-- КВАНЗА МЕДИА БАИНГ ООО | 40702810300000032987
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 410, '40702810300000032987', '044525411', 'ФИЛИАЛ "ЦЕНТРАЛЬНЫЙ" БАНКА ВТБ (ПАО  )', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 410 AND rs = '40702810300000032987');

-- КОМПАНИЯ СИМПЛ ООО | 40702810938040022379
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 381, '40702810938040022379', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 381 AND rs = '40702810938040022379');

-- КОПИРКА24 ООО | 40702810238710009733
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 415, '40702810238710009733', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 415 AND rs = '40702810238710009733');

-- Каминская Дарья Николаевна ИП | 40802810901500354209
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 283, '40802810901500354209', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 283 AND rs = '40802810901500354209');

-- Кудрявцев Алексей Васильевич ИП | 40802810400280006942
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 395, '40802810400280006942', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 395 AND rs = '40802810400280006942');

-- ЛАЙОН КОММЬЮНИКЕЙШНЗ ООО | 40702810500000279628
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 24, '40702810500000279628', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 24 AND rs = '40702810500000279628');

-- ЛИНИЯ КОНСУЛЬТАЦИЙ РУНА ООО | 40702810738110104372
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 338, '40702810738110104372', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 338 AND rs = '40702810738110104372');

-- Лысенко Владимир Леонидович ИП | 40802810600001618289
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 281, '40802810600001618289', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 281 AND rs = '40802810600001618289');

-- МАЙ ПЕРФОМАНС ЭЙДЖЕНСИ ООО | 40702810512010821771
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 110, '40702810512010821771', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 110 AND rs = '40702810512010821771');

-- МАЙЛСТОУН ООО | 40702810138000006148
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 583, '40702810138000006148', '044525974', 'АО "ТБанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 583 AND rs = '40702810138000006148');

-- МАНГО ТЕЛЕКОМ ООО | 40702810506800002283
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 98, '40702810506800002283', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 98 AND rs = '40702810506800002283');

-- МБР ООО | 40702810901520002103
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 391, '40702810901520002103', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 391 AND rs = '40702810901520002103');

-- МБР ООО | 40702810701520001579
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 391, '40702810701520001579', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 391 AND rs = '40702810701520001579');

-- МЕГАБАЙТ ООО | 40702810238720031461
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 323, '40702810238720031461', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 323 AND rs = '40702810238720031461');

-- МЕГАБАЙТ ООО | 40702810202870023492
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 323, '40702810202870023492', '004525988', 'ОКЦ № 1 ГУ Банка России по ЦФО//УФК ПО Г. МОСКВЕ г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 323 AND rs = '40702810202870023492');

-- МЕГАБАЙТ ООО | 40702810838000264536
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 323, '40702810838000264536', '044525593', 'АО "АЛЬФА-БАНК"', 2
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 323 AND rs = '40702810838000264536');

-- МЕГАБАЙТ ООО | 40702810402870021388
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 323, '40702810402870021388', '044525700', 'АО "Райффайзенбанк" г Москва', 3
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 323 AND rs = '40702810402870021388');

-- МЕГАФОН ПАО | 40702810538050107202
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 29, '40702810538050107202', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 29 AND rs = '40702810538050107202');

-- МЕДИА ВЕЛЬЮ АО | 40702810038040101352
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 221, '40702810038040101352', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 221 AND rs = '40702810038040101352');

-- МЕДИА ВЕЛЬЮ АО | 40702810101200002993
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 221, '40702810101200002993', '043510107', 'СИМФЕРОПОЛЬСКИЙ ФИЛИАЛ АБ "РОССИЯ" г Симферополь', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 221 AND rs = '40702810101200002993');

-- МЕДИА ПЛАТФОРМА ООО | 40702810800000083446
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 49, '40702810800000083446', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 49 AND rs = '40702810800000083446');

-- МЕДИАНА БИ ЭЙЧ ООО | 40702810138720024426
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 439, '40702810138720024426', '044525112', 'Московский филиал АБ "РОССИЯ" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 439 AND rs = '40702810138720024426');

-- МЕДИАНА БИ ЭЙЧ ООО | 40702810601400010010
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 439, '40702810601400010010', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 439 AND rs = '40702810601400010010');

-- МЕДИАПУЛ ООО | 40702810238000028259
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 581, '40702810238000028259', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 581 AND rs = '40702810238000028259');

-- МЕДИАСКАУТ ООО | 40702810900001003334
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 30, '40702810900001003334', '042202603', 'ВОЛГО-ВЯТСКИЙ БАНК ПАО СБЕРБАНК г Нижний Новгород', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 30 AND rs = '40702810900001003334');

-- МЕДЭКСПОРТ-СЕВЕРНАЯ ЗВЕЗДА ООО | 40702810323050001150
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 178, '40702810323050001150', '042202603', 'ВОЛГО-ВЯТСКИЙ БАНК ПАО СБЕРБАНК г Нижний Новгород', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 178 AND rs = '40702810323050001150');

-- МЕСТО ВСТРЕЧИ №1 ООО | 40702810438000141402
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 261, '40702810438000141402', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 261 AND rs = '40702810438000141402');

-- МЕСТО ООО | 40702810102370027962
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 600, '40702810102370027962', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 600 AND rs = '40702810102370027962');

-- МУВИ 360 ООО | 40702810038000006138
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 643, '40702810038000006138', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 643 AND rs = '40702810038000006138');

-- НЕНАШЕВ ДЕНИС АЛЕКСАНДРОВИЧ ИП | 40802810200003619796
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 530, '40802810200003619796', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 530 AND rs = '40802810200003619796');

-- НИЖЕГОРОДСКАЯ АПТЕЧНАЯ СЕТЬ ООО | 40702810642020003125
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 276, '40702810642020003125', '044525545', 'АО ЮниКредит Банк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 276 AND rs = '40702810642020003125');

-- НПЦ АВТОМАТИЗАЦИЯ БИЗНЕСА ООО | 40702810138000018084
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 258, '40702810138000018084', '040349602', 'КРАСНОДАРСКОЕ ОТДЕЛЕНИЕ N8619 ПАО СБЕРБАНК г Краснодар', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 258 AND rs = '40702810138000018084');

-- Новиков Ярослав Анатольевич ИП | 40802810900003170991
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 365, '40802810900003170991', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 365 AND rs = '40802810900003170991');

-- ОБРАЗ ООО | 40702810970000015606
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 157, '40702810970000015606', '040813608', 'ДАЛЬНЕВОСТОЧНЫЙ БАНК ПАО СБЕРБАНК г Хабаровск', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 157 AND rs = '40702810970000015606');

-- ОМД НОВУС ООО | 40702810101850003669
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 99, '40702810101850003669', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 99 AND rs = '40702810101850003669');

-- ОМД НОВУС ООО | 40702810787360024862
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 99, '40702810787360024862', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 99 AND rs = '40702810787360024862');

-- ПРЕМЬЕР НУТРИШИНАЛ ООО | 40702810300000071748
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 249, '40702810300000071748', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 249 AND rs = '40702810300000071748');

-- ПРОФБУХ ООО | 40702810002610000024
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 577, '40702810002610000024', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 577 AND rs = '40702810002610000024');

-- ПУГАЧЕВ ДЕНИС ДМИТРИЕВИЧ ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ | 40802810524450000922
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 123, '40802810524450000922', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 123 AND rs = '40802810524450000922');

-- ПФ СКБ КОНТУР АО | 40702810116260100181
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 57, '40702810116260100181', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 57 AND rs = '40702810116260100181');

-- Р-КОНФ ООО | 40702810010001541732
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 78, '40702810010001541732', '044525411', 'ФИЛИАЛ "ЦЕНТРАЛЬНЫЙ" БАНКА ВТБ (ПАО  )', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 78 AND rs = '40702810010001541732');

-- РА АДВИЗОР ООО | 40702810502620001733
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 637, '40702810502620001733', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 637 AND rs = '40702810502620001733');

-- РА СА МЕДИА ООО | 40702810412010028577
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 2, '40702810412010028577', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 2 AND rs = '40702810412010028577');

-- РИГЛА ООО | 40702810442710001161
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 247, '40702810442710001161', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 247 AND rs = '40702810442710001161');

-- РИГЛА ООО | 40702810038060104287
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 247, '40702810038060104287', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 247 AND rs = '40702810038060104287');

-- РОРЕ МЕДИА ООО | 40702810210250001399
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 363, '40702810210250001399', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 363 AND rs = '40702810210250001399');

-- РОСКОМНАДЗОР | 03100643000000019500
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 413, '03100643000000019500', '024501901', 'ОПЕРАЦИОННЫЙ ДЕПАРТАМЕНТ БАНКА РОССИИ//Межрегиональное операционное УФК г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 413 AND rs = '03100643000000019500');

-- РПК ПЛЕЙС ПРИНТ ООО | 40702810902410001459
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 97, '40702810902410001459', '044525411', 'ФИЛИАЛ "ЦЕНТРАЛЬНЫЙ" БАНКА ВТБ (ПАО  )', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 97 AND rs = '40702810902410001459');

-- РС ХЕЛС ООО | 40702810800001450324
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 528, '40702810800001450324', '044030786', 'ФИЛИАЛ "САНКТ-ПЕТЕРБУРГСКИЙ" АО "АЛЬФА-БАНК" г Санкт-Петербург', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 528 AND rs = '40702810800001450324');

-- Руна АО | 40702810238030102569
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 191, '40702810238030102569', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 191 AND rs = '40702810238030102569');

-- САЙТСИНГ ООО | 40702810102800002512
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 173, '40702810102800002512', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 173 AND rs = '40702810102800002512');

-- СДЭК-ГЛОБАЛ ООО | 40702810723000005023
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 569, '40702810723000005023', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 569 AND rs = '40702810723000005023');

-- СЕМЕЙНАЯ АПТЕКА АПРЕЛЬ ООО | 40702810800010000547
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 553, '40702810800010000547', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 553 AND rs = '40702810800010000547');

-- СКАНДИ ЛАЙН ООО | 40702810740170103929
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 66, '40702810740170103929', '044525112', 'Московский филиал АБ "РОССИЯ" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 66 AND rs = '40702810740170103929');

-- СКЛАД ЗДОРОВЬЯ ООО | 40702810710001508088
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 570, '40702810710001508088', '044525411', 'Филиал "Центральный" Банка ВТБ (ПАО) г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 570 AND rs = '40702810710001508088');

-- СЛ МЕДИА ООО | 40702810638040101529
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 608, '40702810638040101529', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 608 AND rs = '40702810638040101529');

-- СОЦИАЛЬНАЯ АПТЕКА ООО | 40702810260320003912
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 376, '40702810260320003912', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 376 AND rs = '40702810260320003912');

-- СПРАВМЕДИКА ООО | 40702810932640004381
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 591, '40702810932640004381', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 591 AND rs = '40702810932640004381');

-- СТИМУЛ ПЛЮС ООО | 40702810745000003825
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 482, '40702810745000003825', '044525360', 'Филиал "Корпоративный" ПАО "Совкомбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 482 AND rs = '40702810745000003825');

-- СТРАТЕГИЯ ФАРМА ООО | 40702810266000033813
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 484, '40702810266000033813', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 484 AND rs = '40702810266000033813');

-- СТРОЙ ФОНД ООО | 40702810402910018507
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 616, '40702810402910018507', '044525068', 'ООО "ОЗОН Банк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 616 AND rs = '40702810402910018507');

-- СУПЕРФАРМА ООО | 40702810170000104278
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 187, '40702810170000104278', '040813608', 'ДАЛЬНЕВОСТОЧНЫЙ БАНК ПАО СБЕРБАНК г Хабаровск', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 187 AND rs = '40702810170000104278');

-- СФЕРА ООО | 40702810922550001078
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 361, '40702810922550001078', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 361 AND rs = '40702810922550001078');

-- Сарбукова Елена Владимировна ИП | 40802810120000607376
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 286, '40802810120000607376', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 286 AND rs = '40802810120000607376');

-- ТАЙМПЭД ЛТД ООО | 40702810610000775792
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 301, '40702810610000775792', '047003608', 'ТУЛЬСКОЕ ОТДЕЛЕНИЕ N8604 ПАО СБЕРБАНК г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 301 AND rs = '40702810610000775792');

-- ТАНДЕР АО | 40702810930010120150
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 552, '40702810930010120150', '044525700', 'АО "Райффайзенбанк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 552 AND rs = '40702810930010120150');

-- ТБАНК АО | 60311810100000044964
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 386, '60311810100000044964', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 386 AND rs = '60311810100000044964');

-- ТЕЛЕМИР ООО | 40702810306800002467
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 27, '40702810306800002467', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 27 AND rs = '40702810306800002467');

-- ТЕЛЕМИР ООО | 40702810606800002594
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 27, '40702810606800002594', '044525112', 'Московский филиал АБ "РОССИЯ" г Москва', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 27 AND rs = '40702810606800002594');

-- ТОП ДИДЖИТАЛ ООО | 40702810914450000690
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 172, '40702810914450000690', '044525232', 'ПАО "МТС-Банк" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 172 AND rs = '40702810914450000690');

-- Тадевосян Гарик Алексеевич ИП | 40802810470010259633
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 404, '40802810470010259633', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 404 AND rs = '40802810470010259633');

-- Тихонин Кирилл Юрьевич ИП | 40802810338000031923
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 94, '40802810338000031923', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 94 AND rs = '40802810338000031923');

-- Тонканов Григорий Михайлович ИП | 40802810700100002543
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 417, '40802810700100002543', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 417 AND rs = '40802810700100002543');

-- УАЙТ БОКС МЕДИА ООО | 40702810900000165332
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 208, '40702810900000165332', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 208 AND rs = '40702810900000165332');

-- УК АС ФАРМИЯ ООО | 40702810520260002572
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 485, '40702810520260002572', '044525593', 'АО "АЛЬФА-БАНК" г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 485 AND rs = '40702810520260002572');

-- УК АС ФАРМИЯ ООО | 40702810220000171501
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 485, '40702810220000171501', '044525593', 'АО "АЛЬФА-БАНК"', 1
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 485 AND rs = '40702810220000171501');

-- УК МАКСАВИТ ООО | 40702810442000019494
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 483, '40702810442000019494', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 483 AND rs = '40702810442000019494');

-- УПРАВЛЯЮЩАЯ КОМПАНИЯ НКС ООО | 40702810101400011331
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 330, '40702810101400011331', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 330 AND rs = '40702810101400011331');

-- ФАРМЛЕНД АО | 40702810900020000043
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 282, '40702810900020000043', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 282 AND rs = '40702810900020000043');

-- ФАРМЛИНК ООО | 40702810400040447960
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 177, '40702810400040447960', '044525225', 'ПАО СБЕРБАНК', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 177 AND rs = '40702810400040447960');

-- ФЬЮЧЕ ЛАБ ООО | 40702810701100013165
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 185, '40702810701100013165', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 185 AND rs = '40702810701100013165');

-- ХАЙЛОАД ЛАБС ООО | 40702810602860006113
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 161, '40702810602860006113', '044525545', 'АО ЮниКредит Банк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 161 AND rs = '40702810602860006113');

-- ШОКОЛАДНАЯ КОРПОРАЦИЯ ООО | 40702810526140000450
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 434, '40702810526140000450', '004525988', 'ОКЦ № 1 ГУ Банка России по ЦФО//УФК ПО Г. МОСКВЕ г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 434 AND rs = '40702810526140000450');

-- ЭМДЖИКОМ ООО | 40702810401100012712
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 36, '40702810401100012712', '044525545', 'АО ЮниКредит Банк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 36 AND rs = '40702810401100012712');

-- ЭМЭМЭС КОММЬЮНИКЕЙШНЗ ООО | 40702810500000280866
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 144, '40702810500000280866', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 144 AND rs = '40702810500000280866');

-- ЮЭМДЖИ ГРУПП ООО | 40702810317060001220
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 495, '40702810317060001220', '017003983', 'ОКЦ № 7 ГУ Банка России по ЦФО//УФК по Тульской области г Тула', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 495 AND rs = '40702810317060001220');

-- Юдина Елена Александровна ИП | 40802810311450002489
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 223, '40802810311450002489', '044525593', 'АО "АЛЬФА-БАНК"', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 223 AND rs = '40802810311450002489');

-- Юматов Михаил Алексеевич ИП | 40802810842000012632
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 119, '40802810842000012632', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 119 AND rs = '40802810842000012632');

-- ЯНДЕКС ООО | 40702810600014307627
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 506, '40702810600014307627', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 506 AND rs = '40702810600014307627');

-- ЯСНЫЙ СВЕТ ООО | 40702810102540003509
INSERT INTO counterparty_bank_accounts (counterparty_id, rs, bik, bank_name, sort_order)
  SELECT 51, '40702810102540003509', '044525225', 'ПАО Сбербанк г Москва', 0
  WHERE NOT EXISTS (
    SELECT 1 FROM counterparty_bank_accounts
    WHERE counterparty_id = 51 AND rs = '40702810102540003509');

-- Итого INSERT bank_accounts: до 148 строк (при отсутствии дублей)

COMMIT;

-- ════════════════════════════════════════════════════════════
-- Проверочные запросы после применения:
-- SELECT id, name, inn, kpp, edo_id FROM counterparties WHERE kpp IS NOT NULL LIMIT 20;
-- SELECT ba.*, cp.name FROM counterparty_bank_accounts ba JOIN counterparties cp ON cp.id=ba.counterparty_id LIMIT 20;
-- ════════════════════════════════════════════════════════════