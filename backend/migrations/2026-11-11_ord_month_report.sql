-- Отчёт ОРД за месяц (владелец 11.11.2026): «Аккаунты → ОРД → Отчёты», таблица по месяцам, выгрузка в Excel и импорт правок.
-- Состав согласован владельцем 11.11.2026. Повторно накатываемая.

-- Снимок разреза DSP «площадка × креатив» за месяц. Сырьё DSP по креативу (`dsp_stat_raw` аналитической базы) живёт месяц
-- (`drop_after 1 month`), суточная сводка разреза по креативу не держит — без снимка показы площадки нельзя разделить по ЕРИД
-- уже через пару недель после конца месяца. Наполняется ежедневно за текущий и прошлый месяц.
CREATE TABLE IF NOT EXISTS ord_erid_month_stat (
    id           SERIAL PRIMARY KEY,
    month        DATE NOT NULL,                                                      -- первое число месяца
    placement_id INTEGER NOT NULL REFERENCES ad_campaign_placement(id) ON DELETE CASCADE,
    creative_id  INTEGER REFERENCES ad_campaign_creative(id) ON DELETE CASCADE,      -- креатив площадки, чей ЕРИД откручен
    erid         VARCHAR(64),                                                        -- ЕРИД креатива на момент снимка
    shows        BIGINT NOT NULL DEFAULT 0,
    clicks       BIGINT NOT NULL DEFAULT 0,
    captured_at  TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_ord_erid_month_stat UNIQUE NULLS NOT DISTINCT (month, placement_id, creative_id)
);
CREATE INDEX IF NOT EXISTS ix_ord_erid_month_stat_month ON ord_erid_month_stat (month);
-- Строка снимка уходит вместе с креативом (ревью 11.11.2026): при SET NULL второй удалённый креатив площадки за месяц упирался
-- в уникальность с NULLS NOT DISTINCT. Пересоздание связи — для базы, где таблица уже создана прежней редакцией.
ALTER TABLE ord_erid_month_stat DROP CONSTRAINT IF EXISTS ord_erid_month_stat_creative_id_fkey;
ALTER TABLE ord_erid_month_stat ADD CONSTRAINT ord_erid_month_stat_creative_id_fkey
    FOREIGN KEY (creative_id) REFERENCES ad_campaign_creative(id) ON DELETE CASCADE;

-- Правки отчёта из Excel поверх расчёта: хранятся только отличия от расчёта. Ключ строки — сделка × площадка × ЕРИД;
-- пустое поле правки — «не правили», значение берётся из расчёта.
CREATE TABLE IF NOT EXISTS ord_report_overrides (
    id           SERIAL PRIMARY KEY,
    month        DATE NOT NULL,                                                      -- первое число месяца
    deal_id      INTEGER REFERENCES sales_deals(id) ON DELETE CASCADE,               -- пусто — код сделки из файла не найден
    deal_code    VARCHAR(16) NOT NULL,                                               -- ID РК, как в файле
    publisher_id INTEGER REFERENCES sales_publishers(id) ON DELETE SET NULL,
    domain       VARCHAR(255) NOT NULL DEFAULT '',                                   -- сайт (домен), как в файле
    erid         VARCHAR(255) NOT NULL DEFAULT '',                                   -- ЕРИД строки, как в расчёте
    kind         VARCHAR(16) NOT NULL,                                               -- правка / добавлена / убрана
    shows        BIGINT,
    clicks       BIGINT,
    amount       NUMERIC(14, 2),                                                     -- сумма на площадку с НДС
    upd_no       VARCHAR(40),
    upd_date     DATE,
    upd_gross    NUMERIC(14, 2),                                                     -- бюджет УПД с НДС
    imported_at  TIMESTAMP NOT NULL DEFAULT now(),
    imported_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    filename     VARCHAR(255),
    CONSTRAINT ck_ord_report_overrides_kind CHECK (kind IN ('правка', 'добавлена', 'убрана'))
);
CREATE INDEX IF NOT EXISTS ix_ord_report_overrides_month ON ord_report_overrides (month);
