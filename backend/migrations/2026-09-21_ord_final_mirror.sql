-- Зеркало доходных договоров кабинета ОРД. Согласовано с владельцем 21.09.2026.
--
-- ЗАЧЕМ. Сопоставление доходных с нашим реестром работало и раньше, но его РЕЗУЛЬТАТ
-- нигде не жил: совпавший договор получал отметку на `contracts.ord_*`, а несовпавший
-- превращался в строку предупреждения в отчёте о загрузке — она умирала вместе с
-- отчётом. Разбирать по ней нельзя: после следующей загрузки список тот же самый, а
-- отметить «этот разобран» негде.
--
-- Замер 21.09.2026 на выгрузке «Изначальные договоры 202609181121.xlsx»: 41 доходный,
-- 34 совпали, 7 нет — и все семеро по СУЩЕСТВУЮЩИМ у нас контрагентам, то есть дело в
-- договоре, а не в юрлице (номер «ПРОВЕРИТЬ», дата 30 февраля, чужая нумерация 306438).
--
-- ССЫЛКИ НА НАШ ДОГОВОР ЗДЕСЬ НЕТ НАМЕРЕННО. Отметка уже живёт на
-- `contracts.ord_contract_id`; вторая колонка с тем же смыслом — два писателя одного
-- факта, и они разойдутся. «Сошёлся» вычисляется соединением по идентификатору в том же
-- контуре, поэтому список сошедшихся и список на разбор — один запрос с разным условием.
--
-- ПОЧЕМУ НЕ `ord_final_contracts`. Это имя занято таблицей ПЕРВОЙ редакции схемы
-- (2026-08-25_ord_mirror.sql), замороженной пустой вместе с `ord_clients`: 0 строк и на
-- стенде, и на проде, код её не читает. Занять её нельзя — там NOT NULL client_id с FK
-- на ord_clients, и вставка потребовала бы снять NOT NULL, смешав две редакции в одной
-- таблице. Замороженное не трогаем, берём своё имя.
CREATE TABLE IF NOT EXISTS ord_final_mirror (
    id              SERIAL PRIMARY KEY,
    ord_id          VARCHAR(64) NOT NULL,
    -- Контур, выдавший идентификатор. Демо и прод дают РАЗНЫЕ id на один договор, и
    -- демовский снаружи неотличим от боевого (см. 2026-08-26_ord_submissions.sql).
    ord_env         VARCHAR(8)  NOT NULL DEFAULT 'prod',
    ord_cid         VARCHAR(64),
    number          TEXT,                  -- как записано в ОРД: встречается и «ПРОВЕРИТЬ»
    date            DATE,
    expiration_date DATE,
    type            VARCHAR(40),
    client_inn      VARCHAR(20),
    client_name     TEXT,
    status          VARCHAR(64),
    status_at       TIMESTAMP,
    error_text      TEXT,
    -- Почему не сошлись: «нет у нас» или список кандидатов при неоднозначности.
    match_note      TEXT,
    -- Состояние разбора. new — не разобран; linked — человек привязал руками;
    -- deferred — отложен с объяснением и в списке на разбор больше не мозолит глаза.
    review_state    VARCHAR(16) NOT NULL DEFAULT 'new',
    review_note     TEXT,
    reviewed_by     INTEGER REFERENCES users(id),
    reviewed_at     TIMESTAMP,
    first_seen_at   TIMESTAMP   NOT NULL DEFAULT now(),
    synced_at       TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ord_final_mirror_id_env
    ON ord_final_mirror (ord_id, ord_env);
CREATE INDEX IF NOT EXISTS idx_ord_final_mirror_review
    ON ord_final_mirror (review_state);
