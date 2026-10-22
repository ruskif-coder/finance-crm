-- Приёмка услуг контура аккаунта по макету «Закрытие по услугам» (14.10; владелец 19.10.2026: «делай»).
-- Что вводит аккаунт, зависит от модели строки МП: CPM — показы и клики; видео — ещё досмотры (VTR считается);
-- фикс — объём пакетами в fact_volume и показы справочно (на деньги не влияют). Себестоимость — на сделку.
-- Отчёт платформы — файл сделки вида «Отчёт» (sales_deal_files.kind = 'report'), отдельной таблицы нет.
-- Повторно накатываемая.
ALTER TABLE final_recon_fact_entries ADD COLUMN IF NOT EXISTS fact_clicks BIGINT CHECK (fact_clicks >= 0);
-- досмотры 100 % (видео); VTR = досмотры / показы — не хранится
ALTER TABLE final_recon_fact_entries ADD COLUMN IF NOT EXISTS fact_views_completed BIGINT CHECK (fact_views_completed >= 0);
-- показы справочно у фикса: для отчёта клиенту, на сумму не влияют
ALTER TABLE final_recon_fact_entries ADD COLUMN IF NOT EXISTS fact_reference_shows BIGINT CHECK (fact_reference_shows >= 0);
-- себестоимость сделки без НДС: вносит аккаунт на закрытии
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS cost_net NUMERIC(14, 2) CHECK (cost_net >= 0);
