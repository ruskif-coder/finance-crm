-- План оплат: отметка «платим в это окно» на операции.
--
-- ПРАКТИКА (владелец 02.11.2026). Из всех неоплаченных списаний человек сам собирает
-- короткий список того, что платит сейчас, — кнопкой «В план» в реестре операций. Это
-- ОТМЕТКА, а не статус: статус «ПЛАН ОПЛАТ» — кредиторская задолженность, его читают
-- отчёты, и смешивать с ним намерение платить нельзя. Срок оплаты отдельно не хранится:
-- у операции есть дата платежа, её человек и ставит.
--
-- Отметку снимает модель (`Operation._paid_leaves_pay_plan`): перевод в «ОПЛАЧЕНО» по любому
-- пути убирает операцию из плана. История входа и выхода — в журнале действий.
--
-- Первичные данные: состав согласован с владельцем 02.11.2026.

ALTER TABLE operations ADD COLUMN IF NOT EXISTS pay_plan_at TIMESTAMP;
ALTER TABLE operations ADD COLUMN IF NOT EXISTS pay_plan_by INTEGER
    REFERENCES users(id) ON DELETE SET NULL;

COMMENT ON COLUMN operations.pay_plan_at IS
    'Когда операцию поставили в план оплат. NULL — не в плане. Снимается при переводе в ОПЛАЧЕНО.';
COMMENT ON COLUMN operations.pay_plan_by IS
    'Кто поставил операцию в план оплат.';

CREATE INDEX IF NOT EXISTS ix_operations_pay_plan ON operations (pay_plan_at)
    WHERE pay_plan_at IS NOT NULL;
