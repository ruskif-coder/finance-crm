-- Кредитная линия ↔ операции (владелец 10.11.2026: «как это в операциях синхронизировать, чтобы висело в ДДС»; «делай все три»).
--
-- 1. Банк-контрагент линии: «выбрано» больше не вводится руками, а считается по ОПЛАЧЕННЫМ операциям тела кредита с этим
--    контрагентом (приход − расход). Ручное `used_amount` заморожено — остаётся для линий без контрагента, новых значений
--    экран в него не пишет.
-- 2. Статья «Тело кредита» с разметкой `loan_body`: тело уходит из P&L, в ДДС оживает плашка «из них N ₽ заёмных».
--    Проценты остаются в «КРЕДИТАХ» (разбор по описанию).
-- Повторно накатываемая.

ALTER TABLE credit_lines ADD COLUMN IF NOT EXISTS counterparty_id INTEGER REFERENCES counterparties(id) ON DELETE SET NULL;
COMMENT ON COLUMN credit_lines.counterparty_id IS 'Банк-контрагент линии: по его операциям статьи с разметкой loan_body считается «выбрано»';
COMMENT ON COLUMN credit_lines.used_amount IS 'Заморожено 10.11.2026: «выбрано» руками — только у линий без контрагента';

INSERT INTO articles (name, "group", type, subgroup, sort_order, pl_line)
SELECT 'Тело кредита', k."group", k.type, k.subgroup, k.sort_order, 'loan_body'
  FROM (SELECT "group", type, subgroup, sort_order, 0 AS o FROM articles WHERE name = 'КРЕДИТЫ'
        UNION ALL SELECT 'ОПЕРАЦИОННЫЕ', 'expense', 'Фин операции', NULL, 1
        ORDER BY o LIMIT 1) k                         -- рядом с «КРЕДИТАМИ»; нет их — в фин. операции
 WHERE NOT EXISTS (SELECT 1 FROM articles WHERE name = 'Тело кредита');
