-- План продаж (владелец 24.10.2026, docs/ПЛАН_план_продаж.md): цели сверху по месяцам и ночной снимок выполнения.
-- Выполнение цели не хранится — считается из сделок (факт + в работе), см. app/sales/plan.py.

-- Цель продаж: месяц × разрез. Разрезы независимые: общая цель, по услуге, по продажнику — три набора цифр, суммы
-- услуг и продажников сверяются с общей на экране (предупреждение, не запрет). Год и кварталы — суммы месяцев.
CREATE TABLE IF NOT EXISTS sales_targets (
    id            SERIAL PRIMARY KEY,
    year          INT      NOT NULL,
    month         SMALLINT NOT NULL CONSTRAINT ck_sales_target_month CHECK (month BETWEEN 1 AND 12),
    scope         TEXT     NOT NULL CONSTRAINT ck_sales_target_scope CHECK (scope IN ('общий', 'услуга', 'продажник')),
    service_id    INT REFERENCES sales_services(id),
    sales_rep_id  INT REFERENCES sales_reps(id),
    amount        NUMERIC(14,2) NOT NULL CONSTRAINT ck_sales_target_amount CHECK (amount >= 0),   -- руб. без НДС
    updated_by    INT REFERENCES users(id),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_sales_target_key CHECK (
         (scope = 'общий'     AND service_id IS NULL     AND sales_rep_id IS NULL)
      OR (scope = 'услуга'    AND service_id IS NOT NULL AND sales_rep_id IS NULL)
      OR (scope = 'продажник' AND service_id IS NULL     AND sales_rep_id IS NOT NULL)),
    CONSTRAINT uq_sales_target UNIQUE NULLS NOT DISTINCT (year, month, scope, service_id, sales_rep_id)
);

-- Ночной снимок выполнения и прогноза по каждой ячейке — для «▲▼ за 7 дней» (истории светофора и стадий для
-- восстановления нет). key_id: id услуги / продажника; 0 — общий и строки «без услуги» / «без продажника».
CREATE TABLE IF NOT EXISTS sales_plan_snapshots (
    day       DATE     NOT NULL,                 -- дата снимка, МСК
    year      INT      NOT NULL,
    month     SMALLINT NOT NULL,
    scope     TEXT     NOT NULL,                 -- 'общий' | 'услуга' | 'продажник' | 'без услуги' | 'без продажника'
    key_id    INT      NOT NULL DEFAULT 0,
    done      NUMERIC(14,2) NOT NULL,            -- факт + в работе
    forecast  NUMERIC(14,2) NOT NULL,            -- + планируемые: зелёный 100 %, оранжевый 50 %
    PRIMARY KEY (day, year, month, scope, key_id)
);

-- Право «План продаж» (владелец 24.10.2026): смотреть — ролям с дашбордом продаж, править — никому (админ проходит
-- проверки сам; руководителю продаж правку выдают в ролях). «Свои / все» — от реестра: «свои» видят общую цель и
-- свою строку продажника.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'sales_plan') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT d.role_id, 'sales_plan', 1, 0, 0, 0, 0, 0, coalesce(r.deals_scope, 'all')
          FROM role_permissions d
          LEFT JOIN role_permissions r ON r.role_id = d.role_id AND r.section = 'sales_registry'
         WHERE d.section = 'sales_dashboard' AND d.can_view = 1;
    END IF;
END $$;
