-- Переписка по площадке запроса на приоритезацию (владелец 04.11.2026: «да, надо» — полная переписка вместо одного поля).
-- До этого замечание площадки и ответ аккаунта жили в одном `prio_placements.comment`, и ответ затирал замечание: на экранах
-- видно было только последнее, история — только в журнале кабинета. Форма — как у переписки сверки
-- (`publisher_request_message`, миграция 2026-10-26_publisher_recon.sql). `prio_placements.comment` остаётся последним
-- сообщением: его читают уведомления и `pub.prio_task_v1`. На 04.11.2026 таблица `prio_placements` на проде пуста —
-- переносить нечего. Повторно накатываемая.

CREATE TABLE IF NOT EXISTS prio_placement_messages (
    id           serial PRIMARY KEY,
    placement_id integer NOT NULL REFERENCES prio_placements(id) ON DELETE CASCADE,
    -- кто пишет: площадка, мы (аккаунт), система
    side         text NOT NULL CHECK (side IN ('площадка', 'мы', 'система')),
    -- что это за ход: по нему экран рисует строку; «чей ход» — по последнему несистемному, как у сверки
    kind         text NOT NULL CHECK (kind IN ('отправка', 'замечание', 'ответ', 'отказ', 'напоминание', 'согласование')),
    -- замечание, ответ, причина отказа; у отправки и согласования может быть пусто
    body         text,
    -- имя и почта автора СНИМКОМ: смена учётки задним числом не переписывает историю
    author_name  text,
    author_email text,
    created_at   timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prio_placement_messages_placement ON prio_placement_messages (placement_id, id);

COMMENT ON TABLE prio_placement_messages IS 'переписка по площадке запроса на приоритезацию — ходы аккаунта и площадки по порядку';

-- Кабинет: переписка своих площадок, пока запрос у площадки. Автор с нашей стороны — «SIMB-AD»: имена сотрудников наружу
-- не отдаём (как pub.recon_message_v1).
CREATE OR REPLACE VIEW pub.prio_message_v1 WITH (security_barrier) AS
SELECT m.id AS message_id, m.placement_id AS prio_id, m.side, m.kind,
       CASE WHEN m.side = 'площадка' THEN m.author_name ELSE 'SIMB-AD' END AS author_name,
       m.body, m.created_at
  FROM prio_placement_messages m
  JOIN prio_placements pp ON pp.id = m.placement_id
 WHERE pp.status = 'у площадки' AND pp.publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.prio_message_v1 TO cabinet;
