-- Аудит 01.10.2026, согласовано владельцем 02.10.2026.
--
-- 1. Когда площадка РК запущена ВПЕРВЫЕ. Письмо «кампания стартовала» уходит площадке
--    один раз — при первом запуске; по статусу «было до» это не определить (площадку
--    могли поставить на паузу или завершить, ни разу не запустив). Пусто — не запускалась.
ALTER TABLE ad_campaign_placement ADD COLUMN IF NOT EXISTS first_started_at timestamp;

-- Уже запускавшиеся (повтор безопасен):
--   · есть настоящие показы — самый надёжный признак; дата — первый день с показами;
--   · сейчас крутят;
--   · живой получатель в сделке «в размещении» — этот признак ставит только запуск
--     (`ad/build.mark_target_placed`).
-- Источники показов — наш счётчик (`ad/stat_sources.OWN`), не верификатор и не демо.
UPDATE ad_campaign_placement p
   SET first_started_at = coalesce(
           (SELECT min(s.date)::timestamp FROM ad_campaign_stat s
             WHERE s.placement_id = p.id AND s.shows > 0 AND s.source IN ('dsp', 'ms', 'manual')),
           p.updated_at, now())
 WHERE p.first_started_at IS NULL
   AND (p.status = 'запущен'
        OR EXISTS (SELECT 1 FROM ad_campaign_stat s
                    WHERE s.placement_id = p.id AND s.shows > 0 AND s.source IN ('dsp', 'ms', 'manual'))
        OR EXISTS (SELECT 1 FROM ad_campaign a
                     JOIN launch_prep_target t ON t.deal_id = a.deal_id
                                              AND t.publisher_id = p.publisher_id
                    WHERE a.id = p.campaign_id AND t.state = 'в размещении'
                      AND t.archived_at IS NULL));

-- 2. Какой площадке адресовано письмо. Отложенное на тихие часы письмо перед отправкой
--    перепроверяет получателя ИМЕННО этой площадки: тот же адрес может быть живым
--    контактом другой. Старым строкам заполнить нечем — у них проверка по адресу.
ALTER TABLE mail_log ADD COLUMN IF NOT EXISTS publisher_id integer
    REFERENCES sales_publishers(id) ON DELETE SET NULL;
