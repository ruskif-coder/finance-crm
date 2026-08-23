-- Единое написание холдингов агентств (2026-08-18).
--
-- Холдинг хранится строкой и сравнивается буквально, поэтому «Media instinct» и
-- «Агентство» — два разных холдинга: группировка разводила по разным корзинам
-- агентства одной группы (сокращение и полное имя).
-- Канонические написания согласованы с владельцем: с владельцем.

UPDATE sales_agencies SET holding = 'Media Instinct'
 WHERE holding IS NOT NULL AND lower(holding) = lower('Media Instinct') AND holding <> 'Media Instinct';

UPDATE sales_agencies SET holding = 'RealWeb'
 WHERE holding IS NOT NULL AND lower(holding) = lower('RealWeb') AND holding <> 'RealWeb';

-- Английское имя MI приведено к тому же написанию, что и холдинг. Поле name не
-- трогаем намеренно: это исходное имя из Битрикса и ключ связи со сделками.
UPDATE sales_agencies SET name_en = 'Media Instinct'
 WHERE name_en IS NOT NULL AND lower(name_en) = lower('Media Instinct') AND name_en <> 'Media Instinct';
