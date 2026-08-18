-- Пробелы по краям имён агентств (2026-08-18).
--
-- Имя компании в Битриксе собирается из этих полей (standard_name), поэтому пробел
-- по краю превращался в двойной разделитель: «Artox Media Digital Group  | Артокс…».
-- Восемь записей: у семи хвостовой/ведущий пробел в name_en, у одной — в name_ru.
-- Сам сборщик имени теперь тоже делает strip, но чинить надо и данные: они видны
-- в справочнике и уедут в Битрикс как есть при любом другом пути записи.
--
-- NULLIF: пустая после обрезки строка — это не имя, а мусор; храним NULL.

UPDATE sales_agencies SET name      = btrim(name)                 WHERE name      <> btrim(name);
UPDATE sales_agencies SET short_name = NULLIF(btrim(short_name), '') WHERE short_name <> btrim(short_name);
UPDATE sales_agencies SET name_en   = NULLIF(btrim(name_en), '')   WHERE name_en   <> btrim(name_en);
UPDATE sales_agencies SET name_ru   = NULLIF(btrim(name_ru), '')   WHERE name_ru   <> btrim(name_ru);
UPDATE sales_agencies SET holding   = NULLIF(btrim(holding), '')   WHERE holding   <> btrim(holding);
