-- Номера документов комплекта, выпущенных 1С (владелец 19.10.2026: «после выпуска имеем номер счёта и УПД»).
-- Заполняет интеграция с 1С (ответ на запрос пакета); до неё пусто — на экране «ждём 1С». Повтор безопасен.
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_invoice_no varchar(40);   -- № счёта в 1С
ALTER TABLE master_deal_upds ADD COLUMN IF NOT EXISTS onec_upd_no varchar(40);       -- № УПД в 1С
