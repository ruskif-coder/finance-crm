-- Кто сделал баннер (владелец 27.09.2026).
--
-- «наш» — баннер собрали мы: он изначально подогнан под наш код и адаптацию.
-- «рекламодатель» — баннер прислал клиент: может быть кривым и с ошибками, и трафик
-- должен проверить его внимательнее — у креатива плашка в конвейере.
--
-- Поле у ФАЙЛА, а не у креатива: вопрос задаётся при каждой загрузке, и первую версию
-- может прислать рекламодатель, а исправленную собрать мы. Признак креатива выводится из
-- его файлов. Уже загруженные остаются пустыми — «не указано», задним числом не выдумываем.

ALTER TABLE launch_prep_creative_file ADD COLUMN IF NOT EXISTS origin varchar(16);

COMMENT ON COLUMN launch_prep_creative_file.origin IS
  'Кто сделал баннер: наш — собрали мы, рекламодатель — прислал клиент (трафику проверить внимательнее). Пусто — не указано (загружено до 27.09.2026).';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'launch_prep_creative_file_origin_check') THEN
    ALTER TABLE launch_prep_creative_file
      ADD CONSTRAINT launch_prep_creative_file_origin_check
      CHECK (origin IS NULL OR origin IN ('наш', 'рекламодатель'));
  END IF;
END $$;
