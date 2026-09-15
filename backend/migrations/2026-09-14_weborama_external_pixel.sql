-- Внешний пиксель Weborama: тег приходит готовым, вставку заводим не мы.
--
-- Решение владельца 14.09.2026, по образцу их выгрузки
-- (`9796_101_Teva_Troxevasin_..._ImpOnly.xlsx`). Разбор файла:
--
--   Insertion name   Simb-ad ePharm network of sites
--   ID insertion     1526
--   Impression tags  https://wcm.weborama-tech.ru/...&a.he=1&a.wi=1&a.hr=p&a.ra=[RANDOM]
--   Comments         только пиксель на показ
--
-- ГЛАВНОЕ ОТЛИЧИЕ ОТ НАШЕГО КОНТУРА — одна вставка на ВСЮ СЕТЬ, а не по вставке на
-- площадку. Поэтому тег хранится на СДЕЛКЕ: значение одно на кампанию, и разложить его
-- по девятнадцати размещениям значило бы завести девятнадцать мест, где одна и та же
-- правда может разойтись.
--
-- При этом различение площадок не теряется: в теге есть `[RANDOM]`, наш сборщик
-- (`app/weborama/naming.final_tag`) подставляет макрос рандомизатора DSP и дописывает
-- `&a.ycp=https://<домен площадки>`, то есть каждая площадка получает свой финальный
-- тег. В ОТЧЁТ к нам эта разбивка не возвращается — у них вставка одна, — отсюда и
-- решение владельца «по внешнему аналитику не собираем, цифры вводим руками на сверке».
--
-- `mode` имеет смысл только при включённом `weborama_pixel`. Умолчание 'own' сохраняет
-- поведение уже сделанного признака: включил галочку — получаешь свой пиксель.

ALTER TABLE sales_deals
    ADD COLUMN IF NOT EXISTS weborama_pixel_mode varchar(10) NOT NULL DEFAULT 'own',
    ADD COLUMN IF NOT EXISTS weborama_pixel_tag text,
    ADD COLUMN IF NOT EXISTS weborama_ext_insertion varchar(32);

COMMENT ON COLUMN sales_deals.weborama_pixel_mode IS
    'own — пиксель получаем сами через API; external — тег принесли готовым. '
    'Осмысленно только при weborama_pixel = true.';
COMMENT ON COLUMN sales_deals.weborama_pixel_tag IS
    'Внешний тег показа, ОДИН на кампанию. Обязан содержать [RANDOM]: тег без '
    'кеш-бастера считает показы неверно, и выясняется это расхождением через месяц.';
COMMENT ON COLUMN sales_deals.weborama_ext_insertion IS
    'Их «ID insertion» из выгрузки — по нему сверяемся с их отчётом.';

-- Значение перечисления держим проверкой, а не на честном слове: mode читают три
-- контура (карточка, DSP, разметка стадий), и опечатка в третьем месте тихо включила бы
-- ветку «свой пиксель» для внешней кампании — то есть мы пошли бы заводить вставку,
-- которая уже заведена клиентом.
ALTER TABLE sales_deals DROP CONSTRAINT IF EXISTS ck_deal_weborama_mode;
ALTER TABLE sales_deals ADD CONSTRAINT ck_deal_weborama_mode
    CHECK (weborama_pixel_mode IN ('own', 'external'));
