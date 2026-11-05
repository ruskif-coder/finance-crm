-- Ссылка на отчёт Weborama у РК с ВНЕШНИМ пикселем (владелец 05.11.2026).
-- Пиксель ставил не наш аккаунт — API к нему у нас нет; клиент делится «постоянной ссылкой» на отчёт
-- (adap-interface.wbrm.ru/…/reportcenter/permalink/link/hash/…). По ней ночью снимаются суточные показы
-- Weborama в сверку (источник weborama_link, в факт не идут). Пусто — ссылки нет, сверка как раньше.
ALTER TABLE ad_campaign ADD COLUMN IF NOT EXISTS wr_report_url TEXT;
COMMENT ON COLUMN ad_campaign.wr_report_url IS 'Постоянная ссылка на отчёт Weborama (внешний пиксель): источник суточных показов для сверки';
