-- Связи креатива РК с конвейером согласования (владелец 04.09.2026).
--
-- До этого у `ad_campaign_creative` был только `file_id` — ссылка на ОДИН файл комплекта.
-- Файлов у комплекта несколько (разные размеры баннера), поэтому по нему нельзя было ни
-- узнать состояние согласования, ни собрать креативы в группу.
--
-- Добавляются две связи, и они отвечают на РАЗНЫЕ вопросы:
--
--   root_set_id — ЛИЧНОСТЬ креатива как рекламного сообщения: корень цепочки доработок
--                 (`launch_prep_creative_set.replaces_set_id`). Владелец: «креатив как
--                 рекламное сообщение един, а правки обычно технические». По нему же
--                 строится обратный вид «креатив → площадки».
--
--   pair_id     — ТЕКУЩАЯ пара «креатив × площадка» этого сообщения. Оттуда берётся
--                 состояние согласования и код пары. При доработке рождается новая пара,
--                 и `pair_id` ПЕРЕСТАВЛЯЕТСЯ, а строка креатива остаётся прежней —
--                 вместе с ЕРИД и хешом DSP (решение владельца: ЕРИД на строку,
--                 технические правки его не меняют).
--
-- Уникальность `(placement_id, root_set_id)` — «одно сообщение на одной площадке». Без
-- неё доработка плодила бы вторую строку, и счётчик «всего» удваивался бы после каждой
-- правки.
--
-- Умолчание статуса переводится на словарь из шести значений (`app/ad/flight.py`):
-- «создан» в него не входит, а свежая строка означает «материал у трафика».
--
-- Безопасно: на 04.09.2026 в таблице 0 строк, переносить нечего.
-- Бэкап: backups/before_ad_creative_links_2026-09-04.sql

ALTER TABLE ad_campaign_creative
  ADD COLUMN IF NOT EXISTS root_set_id integer REFERENCES launch_prep_creative_set(id),
  ADD COLUMN IF NOT EXISTS pair_id     integer REFERENCES launch_prep_pair(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ad_creative_msg
  ON ad_campaign_creative (placement_id, root_set_id);

CREATE INDEX IF NOT EXISTS ix_ad_creative_pair
  ON ad_campaign_creative (pair_id) WHERE pair_id IS NOT NULL;

ALTER TABLE ad_campaign_creative ALTER COLUMN status SET DEFAULT 'у трафика';
