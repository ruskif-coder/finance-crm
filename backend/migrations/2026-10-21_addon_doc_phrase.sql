-- Формулировка доп. услуги в документах (владелец 21.10.2026): подстановка {услуга} в ДС допов и основании закрывающих.
-- Пусто — в документ идёт название со строчной буквы. Повторно накатываемая; стартовое заполнение не затирает правку.
ALTER TABLE sales_addon_services ADD COLUMN IF NOT EXISTS doc_phrase text;
COMMENT ON COLUMN sales_addon_services.doc_phrase IS 'как доп. услуга называется в тексте ДС и основании УПД («изготовление комплекта рекламных материалов»)';

UPDATE sales_addon_services SET doc_phrase = 'изготовление комплекта рекламных материалов'
 WHERE name = 'Комплект рекламных материалов' AND doc_phrase IS NULL;
UPDATE sales_addon_services SET doc_phrase = 'проведение исследования Sales-Lift' WHERE name = 'Sales-Lift' AND doc_phrase IS NULL;
UPDATE sales_addon_services SET doc_phrase = 'проведение исследования Brand-lift' WHERE name = 'Brand-lift' AND doc_phrase IS NULL;
UPDATE sales_addon_services SET doc_phrase = 'верификация показов пикселем Weborama'
 WHERE name = 'Верификация пикселем Weborama' AND doc_phrase IS NULL;
