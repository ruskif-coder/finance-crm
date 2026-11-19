-- Личные настройки вида таблиц (владелец 19.11.2026): первая — колонки таблицы площадок в расхлопе дашборда трафика.
-- Общая таблица на любые такие настройки, ключ — что настраивается («traffic.sites.columns»). Настройка едет за человеком
-- на любой компьютер. Строки нет — действует вид по умолчанию, бэкфилл не нужен. Повторный накат безопасен.
CREATE TABLE IF NOT EXISTS user_ui_prefs (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- что настраивается; список допустимых ключей и форма значения — в app/ui_prefs.py
    key        VARCHAR(64) NOT NULL,
    -- сама настройка; для колонок — {"order": [...], "hidden": [...]}
    value      JSONB NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);
