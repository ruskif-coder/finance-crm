-- Премодерация внешней рекламы SSP (07.11.2026, состав согласован с владельцем).
-- Забираем заявки модерации SSP, согласуем у себя. В SSP решения НЕ отправляем (владелец 07.11:
-- «пока только на получение и согласование») — поле sent_at заведено под будущую отправку.
-- Повторно накатываемая.

-- Пакет: сам креатив, один на все площадки. SSP заводит отдельную заявку на каждую площадку
-- (свой ЕРИД и клик), баннер у них один — смотреть его второй раз нечего.
CREATE TABLE IF NOT EXISTS premod_package (
    id               SERIAL PRIMARY KEY,
    image_hash       VARCHAR(64)  NOT NULL UNIQUE,   -- баннер и заказчик без клика, пикселей, ЕРИД, rnd
    size             VARCHAR(16),                    -- из ad.size: 300x250 / адаптивный / NULL — не объявлен
    kind             VARCHAR(16),                    -- статика / HTML5 / прочее
    advertiser_name  TEXT,                           -- заказчик из сведений для ОРД, как указал SSP
    advertiser_inn   VARCHAR(12),
    snapshot_token   VARCHAR(64),                    -- каталог снимка в песочнице (разметка без счётчиков)
    first_seen_at    TIMESTAMP    NOT NULL DEFAULT now()
);

-- Заявка SSP: одна запись модерации SSP (одна-две площадки, свой ЕРИД).
CREATE TABLE IF NOT EXISTS premod_request (
    id                SERIAL PRIMARY KEY,
    ssp_uuid          VARCHAR(64)  NOT NULL UNIQUE,
    package_id        INTEGER      REFERENCES premod_package(id),  -- сменилась разметка у SSP → новый пакет
    erid              VARCHAR(64),
    crid              VARCHAR(128),
    ssp_publishers    INTEGER[]    NOT NULL DEFAULT '{}',          -- id площадок у SSP, как есть
    ssp_status        SMALLINT,                                    -- у SSP: 0 ждёт, 1 одобрено, 2 отклонено
    ssp_updated_at    TIMESTAMP,
    ssp_moderated_by  TEXT,
    preview_url       TEXT,
    click_url         TEXT,
    landing           TEXT,                                        -- раскодированная посадочная
    checks            JSONB        NOT NULL DEFAULT '[]',          -- автопроверки: ЕРИД, ОРД, размер, хосты
    fetched_at        TIMESTAMP    NOT NULL DEFAULT now(),         -- когда забрали разметку
    last_seen_at      TIMESTAMP    NOT NULL DEFAULT now()          -- последний раз видели в списке SSP
);
CREATE INDEX IF NOT EXISTS ix_premod_request_package ON premod_request (package_id);

-- Наше решение. Только добавление: история не перетирается, новая версия креатива — новое решение.
CREATE TABLE IF NOT EXISTS premod_decision (
    id                SERIAL PRIMARY KEY,
    request_id        INTEGER      NOT NULL REFERENCES premod_request(id),
    image_hash        VARCHAR(64)  NOT NULL,          -- по какой версии креатива решали
    verdict           VARCHAR(16)  NOT NULL CHECK (verdict IN ('одобрено', 'отклонено')),
    reason_code       INTEGER,                        -- пункт дерева причин SSP (только у отказа)
    reason_label      TEXT,                           -- его название на момент решения
    comment           TEXT,
    decided_by        INTEGER      NOT NULL REFERENCES users(id),
    decided_at        TIMESTAMP    NOT NULL DEFAULT now(),
    followed_package  BOOLEAN,                        -- повторил прежнее решение пакета; NULL — прежнего не было
    sent_at           TIMESTAMP                       -- отправлено в SSP; пока всегда NULL
);
CREATE INDEX IF NOT EXISTS ix_premod_decision_request ON premod_decision (request_id);

-- Право «Трафики · Премодерация»: просмотр и правка (согласование). Владелец 07.11: «Админ Трафик» и «Трафик».
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'traffic_premod') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'traffic_premod', 1, 0, 1, 0, 0, 0, 'all'
          FROM roles r
         WHERE r.key IN ('role_14', 'role_13');
    END IF;
END $$;

-- ── Экран по макету (владелец 08.11.2026: состав подтверждён) ──
-- Распознавания текста с картинки нет (замер 07.11: мелкую юридическую строку не читает): у статики
-- проверки текста — «посмотреть глазами», текст есть только у HTML5 (из разметки).
ALTER TABLE premod_package ADD COLUMN IF NOT EXISTS text TEXT;                        -- видимый текст HTML5; у статики NULL
ALTER TABLE premod_package ADD COLUMN IF NOT EXISTS checks JSONB NOT NULL DEFAULT '[]';  -- проверки пакета: пометка, рекламодатель, предупреждение, стоп-слова, ЕРИД…
ALTER TABLE premod_package ADD COLUMN IF NOT EXISTS prev_package_id INTEGER REFERENCES premod_package(id);  -- прежняя версия этого креатива
ALTER TABLE premod_package ADD COLUMN IF NOT EXISTS changes JSONB;                    -- что изменилось против прежней версии

ALTER TABLE premod_decision ADD COLUMN IF NOT EXISTS bulk BOOLEAN NOT NULL DEFAULT false;  -- принято «Одобрить чистые» разом

-- Заказчики премодерации. Не наши рекламодатели (их ИНН в реестре продаж нет) — свой справочник.
CREATE TABLE IF NOT EXISTS premod_advertiser (
    inn         VARCHAR(12) PRIMARY KEY,
    short_name  TEXT,          -- короткое имя для очереди
    category    TEXT           -- «лекарства» / «БАД» требуют своего предупреждения; иначе любое слово или пусто
);
