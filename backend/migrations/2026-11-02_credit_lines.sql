-- Кредитные линии — для «Денег на сегодня» в сводке плана оплат (хендофф «План оплат · виджеты сводки», состав
-- утверждён владельцем 02.11.2026).
--
-- «Выбрано» вводится руками: тело кредита в статьях не выделено (есть только проценты), из операций его не вычислить.
-- Поэтому рядом лежит дата, на которую цифра верна, — устаревшая цифра должна быть видна как устаревшая.
-- Закрытая линия не удаляется, а выключается: в расчёт не идёт, история остаётся.
-- Правится в «Настройки → Остатки» под тем же правом (`settings_balances`), что и стартовые остатки банков.
-- Повторно накатываемая.

CREATE TABLE IF NOT EXISTS credit_lines (
    id           serial PRIMARY KEY,
    bank         varchar NOT NULL,                       -- тем же словом, что в операциях: «АльфаБанк»
    limit_amount numeric(15, 2) NOT NULL,                -- лимит линии
    used_amount  numeric(15, 2) NOT NULL DEFAULT 0,      -- сколько выбрано
    as_of        date,                                   -- на какую дату «выбрано» верно
    note         text,                                   -- договор, ставка, срок
    is_active    boolean NOT NULL DEFAULT true,          -- закрытая линия в расчёт не идёт
    updated_at   timestamp NOT NULL DEFAULT now(),
    updated_by   integer REFERENCES users(id) ON DELETE SET NULL
);

COMMENT ON TABLE credit_lines IS 'Кредитные линии: свободный остаток лимита = limit_amount - used_amount (сводка плана оплат)';
COMMENT ON COLUMN credit_lines.used_amount IS 'Выбрано по линии; вводится руками — тело кредита в статьях не выделено';
COMMENT ON COLUMN credit_lines.as_of IS 'На какую дату верно «выбрано»';
