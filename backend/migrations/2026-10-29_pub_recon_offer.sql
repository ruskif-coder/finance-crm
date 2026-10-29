-- Кабинет · сверка: кнопка «Согласен с N» показывает ровно то N, которое зафиксирует согласие (ревью 29.10.2026).
-- С 29.10 «Согласен» площадки без спора — это итог. Бэкенд (`publisher_recon.service.publisher_answer`) берёт последнее
-- НАШЕ сообщение С ЦИФРОЙ, а витрина брала последнее сообщение целиком: предложили N, потом ответили текстом — кабинет
-- показывал нашу цифру, а фиксировалось N. Теперь `offer` — по тому же правилу, что и бэкенд. Остальное без изменений.
-- Повторно накатываемая.

CREATE OR REPLACE VIEW pub.recon_v1 WITH (security_barrier) AS
SELECT r.id AS request_id, r.publisher_id, pb.domain AS site, r.period, r.asked_at, r.due_at,
       r.verdict, r.decided_at,
       rc.our_volume, rc.their_volume, rc.agreed_volume, COALESCE(rc.cpm, pb.cpm_contract)::numeric AS cpm,
       COALESCE(lm.side, 'система') AS last_side,
       CASE WHEN lm.side = 'мы' THEN
         (SELECT m.volume FROM publisher_request_message m
           WHERE m.request_id = r.id AND m.side = 'мы' AND m.volume IS NOT NULL ORDER BY m.id DESC LIMIT 1)
       END AS offer,
       (SELECT count(*) FROM publisher_request_message m
         WHERE m.request_id = r.id AND m.side <> 'площадка'
           AND m.created_at > COALESCE(r.pub_seen_at, '-infinity'::timestamp)) AS unread,
       (SELECT count(*) FROM publisher_request_message m WHERE m.request_id = r.id AND m.side <> 'система') AS messages
  FROM publisher_request r
  JOIN sales_publishers pb ON pb.id = r.publisher_id
  LEFT JOIN publisher_recon rc ON rc.request_id = r.id
  LEFT JOIN LATERAL (SELECT m.side FROM publisher_request_message m
                      WHERE m.request_id = r.id AND m.side <> 'система' ORDER BY m.id DESC LIMIT 1) lm ON true
 WHERE r.kind = 'сверка' AND r.publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.recon_v1 TO cabinet;
