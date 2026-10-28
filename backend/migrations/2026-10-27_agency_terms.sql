-- «Агентские условия» (владелец 27.10.2026, схема — docs/СХЕМА_СК.md): правила СК, спец. условия, закрытый месяц.
-- Повторно накатываемая.

-- Правило СК — набор необязательных признаков; сделке подходит правило, чьи заданные признаки с ней совпадают, побеждает
-- правило с наибольшим числом признаков («чем больше условий задано — тем точнее расчёт»). Основная СК — база договор +
-- агентство (или рекламодатель при прямом договоре), уточнения брендом и услугой; партнёрская — отдельная выплата получателю.
CREATE TABLE IF NOT EXISTS sk_rules (
    id            serial PRIMARY KEY,
    kind          varchar(12) NOT NULL CHECK (kind IN ('основная', 'партнёрская')),
    contract_id   integer REFERENCES contracts(id),
    agency_id     integer REFERENCES sales_agencies(id),
    advertiser_id integer REFERENCES sales_advertisers(id),
    brand_id      integer REFERENCES sales_brands(id),
    service_id    integer REFERENCES sales_services(id),
    recipient_id  integer REFERENCES counterparties(id),          -- кому платим партнёрскую; у основной — контрагент договора
    mode          varchar(16) NOT NULL CHECK (mode IN ('постоплата', 'скидка в счёт')),
    percent       numeric(5,2) NOT NULL CHECK (percent >= 0 AND percent <= 100),
    valid_from    date NOT NULL,                                   -- действует с: прошлые месяцы — по правилам того времени
    valid_to      date,                                            -- по; пусто — бессрочно
    note          text,
    created_at    timestamp NOT NULL DEFAULT now(),
    created_by    integer REFERENCES users(id),
    updated_at    timestamp,
    updated_by    integer REFERENCES users(id),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CHECK (kind <> 'основная' OR (contract_id IS NOT NULL AND (agency_id IS NOT NULL OR advertiser_id IS NOT NULL))),
    CHECK (kind <> 'партнёрская' OR (recipient_id IS NOT NULL AND (contract_id IS NOT NULL OR agency_id IS NOT NULL
           OR advertiser_id IS NOT NULL OR brand_id IS NOT NULL OR service_id IS NOT NULL)))
);
CREATE INDEX IF NOT EXISTS ix_sk_rules_contract ON sk_rules (contract_id);
CREATE INDEX IF NOT EXISTS ix_sk_rules_advertiser ON sk_rules (advertiser_id);

-- Спец. условия — скрытая вкладка (право sk_special); в общий расчёт не подмешиваются.
CREATE TABLE IF NOT EXISTS sk_special_terms (
    id          serial PRIMARY KEY,
    scope_kind  varchar(16) NOT NULL CHECK (scope_kind IN ('договор', 'агентство', 'рекламодатель', 'бренд')),
    scope_id    integer NOT NULL,                                  -- id договора / агентства / рекламодателя / бренда
    title       text NOT NULL,                                     -- что за условие: бонус за объём, ретро и т. п.
    percent     numeric(5,2),                                      -- % — или…
    amount      numeric(14,2),                                     -- …фиксированная сумма
    valid_from  date NOT NULL,
    valid_to    date,
    note        text,
    created_at  timestamp NOT NULL DEFAULT now(),
    created_by  integer REFERENCES users(id),
    updated_at  timestamp,
    updated_by  integer REFERENCES users(id),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

-- Закрытый месяц: СК считается на момент закрытия месяца по сделкам, прошедшим согласования в ДО, и фиксируется снимком —
-- правка правил закрытый месяц не меняет.
CREATE TABLE IF NOT EXISTS sk_months (
    period     varchar(7) PRIMARY KEY,                             -- YYYY-MM
    closed_at  timestamp NOT NULL DEFAULT now(),
    closed_by  integer REFERENCES users(id),
    note       text
);

CREATE TABLE IF NOT EXISTS sk_accruals (
    id              serial PRIMARY KEY,
    period          varchar(7) NOT NULL REFERENCES sk_months(period) ON DELETE CASCADE,
    deal_id         integer NOT NULL REFERENCES sales_deals(id),
    master_deal_id  integer REFERENCES master_deals(id),
    kind            varchar(12) NOT NULL CHECK (kind IN ('основная', 'партнёрская')),
    rule_id         integer REFERENCES sk_rules(id),               -- сработавшее правило; NULL — «условие не задано»
    recipient_id    integer REFERENCES counterparties(id),
    mode            varchar(16),
    percent         numeric(5,2),
    base_net        numeric(14,2) NOT NULL,                        -- сумма ДС без НДС до вычета скидки
    amount_net      numeric(14,2)                                  -- СК, ₽
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sk_accruals ON sk_accruals (period, deal_id, kind, coalesce(recipient_id, 0));
CREATE INDEX IF NOT EXISTS ix_sk_accruals_deal ON sk_accruals (deal_id);

-- Права (владелец 27.10.2026): базовые вкладки смотрят продажи и аккаунты, правят мастера; спец. условия — Мастер Сейлз
-- и «Просто Лев» (смотрят и правят). Новый раздел запрещён всем по умолчанию — бэкфилл по ключам ролей.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'sk_terms') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'sk_terms', 1, 0, CASE WHEN r.key IN ('role_5', 'role_9') THEN 1 ELSE 0 END, 0, 0, 0, 'all'
          FROM roles r WHERE r.key IN ('role_5', 'role_7', 'role_8', 'role_9');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'sk_special') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'sk_special', 1, 0, 1, 0, 0, 0, 'all'
          FROM roles r WHERE r.key IN ('role_5', 'viewer');
    END IF;
END $$;

-- Порог спец. условия (хендофф 27.10.2026, решение владельца): «3 % при обороте от 30 млн за год». Оборот — сумма ДС без НДС
-- закрытых сделок объекта привязки нарастающим с начала календарного года; когда порог пройден, % начисляется со всего
-- оборота года задним числом, дальше — с оборота каждого месяца. Пусто — % без порога.
ALTER TABLE sk_special_terms ADD COLUMN IF NOT EXISTS threshold numeric(14,2);

-- «Условия работы» (владелец 27.10.2026): договорённости с агентствами и рекламодателями, которые аккаунт учитывает при
-- сборке медиаплана (фиксированный CPM, бонусные отчёты, деление бюджета…). Признаки необязательны, хотя бы один; в
-- конструкторе МП под брифом показываются ВСЕ подходящие сделке условия, точные выше. Права — как у «Агентских условий».
CREATE TABLE IF NOT EXISTS sk_work_terms (
    id             serial PRIMARY KEY,
    contract_id    integer REFERENCES contracts(id),
    agency_id      integer REFERENCES sales_agencies(id),
    advertiser_id  integer REFERENCES sales_advertisers(id),
    brand_id       integer REFERENCES sales_brands(id),
    service_id     integer REFERENCES sales_services(id),
    body           text NOT NULL,                                  -- текст условия
    mail_subject   text,                                           -- тема письма, где договорились
    commit_net     numeric(14,2),                                  -- коммит бюджета, ₽ без НДС
    comment        text,
    valid_from     date NOT NULL,
    valid_to       date,
    created_at     timestamp NOT NULL DEFAULT now(),
    created_by     integer REFERENCES users(id),
    updated_at     timestamp,
    updated_by     integer REFERENCES users(id),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CHECK (contract_id IS NOT NULL OR agency_id IS NOT NULL OR advertiser_id IS NOT NULL OR brand_id IS NOT NULL OR service_id IS NOT NULL)
);
