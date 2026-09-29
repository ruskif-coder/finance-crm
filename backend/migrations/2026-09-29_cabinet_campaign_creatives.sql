-- Кабинет паблишера → «Актуальные кампании»: согласованные креативы размещения —
-- для предпросмотра (глаз) и отзыва согласования площадкой (владелец 29.09.2026).
--
-- Отзыв согласования = просьба к аккаунту переделать баннер по стандартной процедуре:
-- вердикт площадки становится «на доработку». Можно, пока размещение площадки не
-- запущено — та же граница, что у нашего отзыва креатива (app/launch_prep/withdraw.py).
-- Представление, первичные данные не меняются. Повторно накатываемое.

CREATE OR REPLACE VIEW pub.campaign_creative_v1 WITH (security_barrier) AS
SELECT p.id                    AS task_id,
       t.id                    AS placement_id,      -- тот же ключ, что у pub.campaign_v1
       t.publisher_id,
       s.no                    AS creative_no,
       s.title                 AS creative_title,
       s.form,
       p.agreed_at,
       -- Отозвать можно, пока размещение площадки не запущено: ни получатель, ни
       -- размещение РК ещё не «в работе». Расчёт повторяет withdraw.blocker; правило
       -- проверяет ещё раз ядро при самом отзыве — здесь только подсказка кнопке.
       (t.state NOT IN ('в размещении', 'завершён', 'сверка завершена', 'архив')
        AND NOT EXISTS (
            SELECT 1 FROM ad_campaign_placement pl
              JOIN ad_campaign c ON c.id = pl.campaign_id
             WHERE c.deal_id = t.deal_id AND pl.publisher_id = t.publisher_id
               AND pl.status IN ('запущен', 'пауза', 'завершена')))  AS revocable
  FROM launch_prep_review r
  JOIN launch_prep_pair p ON p.id = r.pair_id
  JOIN launch_prep_creative_set s ON s.id = p.set_id
  JOIN launch_prep_target t ON t.id = p.target_id
 WHERE r.kind = 'площадка' AND r.verdict = 'ок'
   AND p.withdrawn_at IS NULL
   AND t.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.campaign_creative_v1 TO cabinet;
