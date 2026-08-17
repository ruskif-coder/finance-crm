-- Дашборд аккаунта: SLA стадий, срыв как отдельный исход, история стадий, отложенные.
-- Хендофф docs/«кабинет аккаунта v1.zip» (README = ТЗ), части 1.2/1.5/1.6.
-- Накатывать ДО выкладки кода: urgency.py читает sla_days и is_lost.

BEGIN;

-- ── SLA ───────────────────────────────────────────────────────────────────
-- Сколько сделка может стоять на стадии, прежде чем стать просрочкой (правило 5
-- срочности: > SLA → «скоро», > 2×SLA → «просрочено»).
-- Каскад: стадия ?? этап ?? дефолт по stage_key из STAGE_CATALOG (код).
-- NULL = «наследуй уровнем выше». 0 = «здесь срока нет» (терминальные, «В размещении»)
-- — иначе забытая строка молча выключала бы проверку, и сделка стояла бы вечно.
ALTER TABLE sales_stage_phases ADD COLUMN IF NOT EXISTS sla_days integer;
ALTER TABLE sales_stages       ADD COLUMN IF NOT EXISTS sla_days integer;

-- ── Срыв ≠ терминальность ────────────────────────────────────────────────
-- Терминальных исходов два: положительный (архив) и срыв. is_terminal говорит
-- «дальше не двигаем», is_lost — «сделка провалена». Светофор красит срыв красной
-- штриховкой, а не серой «требует разбора»: у сорванной стадии stage_key пуст,
-- и без этого флага она неотличима от несопоставленной.
ALTER TABLE sales_stages ADD COLUMN IF NOT EXISTS is_lost boolean NOT NULL DEFAULT false;

-- ── История стадий ───────────────────────────────────────────────────────
-- На ней строится аналитика «сколько сделка живёт на стадии» → уточнение sla_days
-- по факту, и восстановление «кто двинул». from_stage_id NULL — первая постановка.
CREATE TABLE IF NOT EXISTS sales_deal_stage_history (
    id            serial PRIMARY KEY,
    deal_id       integer NOT NULL REFERENCES sales_deals(id) ON DELETE CASCADE,
    from_stage_id integer REFERENCES sales_stages(id),
    to_stage_id   integer NOT NULL REFERENCES sales_stages(id),
    user_id       integer,
    at            timestamptz NOT NULL DEFAULT now(),
    reason        text
);
CREATE INDEX IF NOT EXISTS ix_deal_stage_history_deal ON sales_deal_stage_history (deal_id, at);

-- ── Отложенные ───────────────────────────────────────────────────────────
-- «Вернуть к дате»: пока return_at в будущем, сделка уходит из очереди в свёрнутую
-- группу «Отложено» и возвращается сама. Одна запись на сделку (перезапись):
-- две даты возврата на одну сделку сделали бы очередь неоднозначной.
-- return_at NULL = заметка без снятия из очереди (иконка-скрепка).
CREATE TABLE IF NOT EXISTS sales_deal_snooze (
    id         serial PRIMARY KEY,
    deal_id    integer NOT NULL UNIQUE REFERENCES sales_deals(id) ON DELETE CASCADE,
    note       text,
    return_at  date,
    author_id  integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_deal_snooze_return ON sales_deal_snooze (return_at);

-- ── Разметка существующих 16 стадий (согласована с владельцем 2026-08-17) ──
-- По id, а не по имени: имена стадий в проекте меняются при кадровых перестановках.

-- Срывы: «Сделка не случилась» (Песочница), «Сделка сорвалась» (Услуги).
UPDATE sales_stages SET is_lost = true WHERE id IN (4, 9);

-- Архив успешных сделок был is_terminal = false — недоделка сида: положительный
-- исход терминален по определению, иначе «Двинуть» ведёт сделку за архив.
UPDATE sales_stages SET is_terminal = true WHERE id = 16;

-- SLA на этапах: Песочница 2 дня, Услуги 5, Документооборот 5.
UPDATE sales_stage_phases SET sla_days = 2 WHERE sort_order = 0;
UPDATE sales_stage_phases SET sla_days = 5 WHERE sort_order = 1;
UPDATE sales_stage_phases SET sla_days = 5 WHERE sort_order = 2;

-- Точечные переопределения на стадиях.
UPDATE sales_stages SET sla_days = 5 WHERE id = 3;   -- МП Отправлено: ждём клиента
UPDATE sales_stages SET sla_days = 0 WHERE id = 7;   -- В размещении: РК идёт, стоять нормально
UPDATE sales_stages SET sla_days = 3 WHERE id = 8;   -- Предварительная сверка
UPDATE sales_stages SET sla_days = 0 WHERE id = 15;  -- Оплата: срок от отсрочки, не от SLA
UPDATE sales_stages SET sla_days = 0 WHERE id IN (4, 9, 16);  -- терминальные

COMMIT;
