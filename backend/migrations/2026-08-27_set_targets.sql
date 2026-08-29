-- Список площадок принадлежит КРЕАТИВУ, а не сделке.
--
-- ЧТО БЫЛО СЛОМАНО. `launch_prep_target` — пара «сделка × площадка», и неотправленный
-- комплект показывал ВСЕ площадки сделки. Отсюда три жалобы владельца 27.08.2026, и все
-- три — одно и то же: площадка, добавленная во второй креатив, появлялась и в первом;
-- снятая — исчезала у обоих; «свой» состав у креатива получить было нельзя в принципе.
--
-- ЧТО ОСТАЁТСЯ У СДЕЛКИ. Сама площадка: её состояние (согласование → ЕРИД → в
-- размещении) и посадочная страница. Это свойства площадки В КАМПАНИИ, а не конкретного
-- баннера: ЕРИД получает площадка, ссылка ведёт на её страницу, и второго ответа на
-- вопрос «где эта площадка» быть не должно. Отвергнутый вариант «добавить set_id прямо
-- в launch_prep_target» дал бы у одной площадки по состоянию и по ссылке на каждый
-- креатив — и однозначного ответа не осталось бы.
--
-- ЧТО ОТВЕЧАЕТ НОВАЯ ТАБЛИЦА. Ровно один вопрос: какому креативу эта площадка адресована.
CREATE TABLE IF NOT EXISTS launch_prep_set_target (
    id         serial PRIMARY KEY,
    set_id     integer NOT NULL REFERENCES launch_prep_creative_set(id) ON DELETE CASCADE,
    target_id  integer NOT NULL REFERENCES launch_prep_target(id) ON DELETE CASCADE,
    added_at   timestamp DEFAULT now()
);

-- Одна площадка входит в креатив один раз. Ограничение, а не проверка в коде: адресат
-- вдвойне дал бы вдвое больше пар при отправке и удвоил бы знаменатель порога ЕРИД.
CREATE UNIQUE INDEX IF NOT EXISTS uq_lp_set_target
    ON launch_prep_set_target (set_id, target_id);
CREATE INDEX IF NOT EXISTS ix_lp_set_target_set ON launch_prep_set_target (set_id);

-- ── бэкфилл: то же, что экран показывал до сих пор ──────────────────────────
-- У ОТПРАВЛЕННОГО комплекта состав уже зафиксирован парами — берём их.
INSERT INTO launch_prep_set_target (set_id, target_id)
SELECT p.set_id, p.target_id FROM launch_prep_pair p
ON CONFLICT DO NOTHING;

-- У НЕОТПРАВЛЕННОГО составом были все площадки сделки (для персонального комплекта —
-- только его площадка). Переносим ровно это, чтобы правка не поменяла ни одного экрана.
INSERT INTO launch_prep_set_target (set_id, target_id)
SELECT s.id, t.id
  FROM launch_prep_creative_set s
  JOIN launch_prep_target t ON t.deal_id = s.deal_id
 WHERE NOT EXISTS (SELECT 1 FROM launch_prep_pair p WHERE p.set_id = s.id)
   AND (s.publisher_id IS NULL OR s.publisher_id = t.publisher_id)
ON CONFLICT DO NOTHING;
