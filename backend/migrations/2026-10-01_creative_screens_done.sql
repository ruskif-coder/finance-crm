-- «Скрины запуска сняты» на строке «креатив × площадка» РК (владелец 01.10.2026).
-- Трафик отмечает, что снял скриншоты креатива на площадке после запуска. Пусто — не сняты.
-- Отметку можно снять: тогда обе колонки снова пустые.
ALTER TABLE ad_campaign_creative ADD COLUMN IF NOT EXISTS screens_done_at timestamp;
ALTER TABLE ad_campaign_creative ADD COLUMN IF NOT EXISTS screens_done_by integer REFERENCES users(id) ON DELETE SET NULL;
