-- Балансировщик (вкладка «Трафики → Админка → Балансировщик»): расчётный индекс ёмкости
-- площадки НА ПОВЕРХНОСТЬ. Согласовано владельцем 02.09.2026.
--
-- Зерно (площадка × scope) зеркалит sales_publisher_traffic.scope — веса web и app правятся
-- отдельно: услуги привязаны к поверхности, объём подключений различается сильно. Вешать индекс
-- на sales_publisher_surfaces/_platforms не стали: вышла бы асимметрия (web на поверхности,
-- ios/android на платформе), а платформы заведены у одной площадки из 41.
--
-- Индекс — АБСОЛЮТНАЯ ёмкость (показов/мес), а не доля: доля считается уже внутри РК от
-- участвующих площадок (ad_campaign_placement.weight → share). Иначе выпадение одной площадки
-- заставляло бы править индексы всем.
--
-- Формула (пересчёт index_auto):
--   ёмкость = запросы рекламного кода                                  → source='ad_requests'
--           = объём × COALESCE(глубина, balance_depth_default) × balance_k → source='estimate'
-- Действующий индекс = COALESCE(index_manual, index_auto).
-- Коэффициенты заведены ПУСТЫМИ: владелец впишет их в интерфейсе после импорта свежих замеров
-- (наблюдаемые 9–23 запроса на уника — всего 2 точки, константу из них не выводим).
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS publisher_balance_index (
    id            SERIAL PRIMARY KEY,
    publisher_id  INTEGER NOT NULL REFERENCES sales_publishers(id) ON DELETE CASCADE,
    scope         VARCHAR(16) NOT NULL,        -- web | app_android | app_ios
    index_auto    DOUBLE PRECISION,            -- пересчитывается формулой
    index_manual  DOUBLE PRECISION,            -- правка рукой; NULL = не правили
    is_locked     BOOLEAN NOT NULL DEFAULT FALSE,  -- не перетирать пересчётом
    source        VARCHAR(16),                 -- ad_requests | estimate | manual
    note          TEXT,
    calculated_at TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT now(),
    updated_by    INTEGER REFERENCES users(id),
    UNIQUE (publisher_id, scope)
);
CREATE INDEX IF NOT EXISTS ix_balance_index_pub ON publisher_balance_index (publisher_id);

-- Коэффициенты оценки — ПУСТЫЕ до решения владельца (пустая строка = «не задан»,
-- оценочная ветка не считается, в интерфейсе прочерк вместо выдуманного числа).
INSERT INTO company_settings (key, value)
SELECT 'balance_k', ''
WHERE NOT EXISTS (SELECT 1 FROM company_settings WHERE key = 'balance_k');

INSERT INTO company_settings (key, value)
SELECT 'balance_depth_default', ''
WHERE NOT EXISTS (SELECT 1 FROM company_settings WHERE key = 'balance_depth_default');
