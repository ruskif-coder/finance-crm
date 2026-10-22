-- «Закрыть без документов» (владелец 19.10.2026): бонусное размещение — сумма к закрытию 0 ₽ (МП целиком бонусный / скидка 100 %).
-- Сверка замораживается как при «Отправить в ДО», в мастер-сделку, ДС и 1С сделка не попадает, сразу «Архив успешных сделок».
-- Повторно накатываемая.
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS closed_no_docs_at TIMESTAMP;
ALTER TABLE final_recon_deals ADD COLUMN IF NOT EXISTS closed_no_docs_by INTEGER REFERENCES users(id);
