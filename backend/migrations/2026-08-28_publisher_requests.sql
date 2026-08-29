-- Тикеты к площадке: сверка объёма за месяц и продление кампании.
-- Состав согласован владельцем 28.08.2026.
--
-- ФОРМА ОДНА на два вида, и это не экономия таблиц. У сверки и продления один жизненный
-- цикл: спросили — ждём — ответили. Две таблицы означали бы дважды написать «кто молчит
-- третий день», дважды посчитать срок и однажды разойтись в этих двух копиях.
--
-- Отличаются они тем, ЧТО спрашивают, и это выражено полями: у сверки заполнен `period`
-- и есть строка чисел, у продления — `deal_id`.

CREATE TABLE IF NOT EXISTS publisher_request (
    id            serial PRIMARY KEY,
    kind          text NOT NULL,                    -- сверка | пролонгация
    publisher_id  integer NOT NULL REFERENCES sales_publishers(id) ON DELETE RESTRICT,
    -- Продление: какую кампанию продлеваем. У сверки пусто — она про месяц целиком.
    deal_id       integer REFERENCES sales_deals(id) ON DELETE CASCADE,
    -- Сверка: 'YYYY-MM'. Ключ сверки — пара «площадка × месяц» (владелец 28.08.2026):
    -- месяц оплачивается ОДНИМ платежом без разбивки по кампаниям, поэтому площадка
    -- подтверждает одну цифру, а кампании внутри — детализация.
    period        text,
    asked_at      timestamp NOT NULL DEFAULT now(),
    due_at        date,
    -- Пустой вердикт означает «спросили, ответа нет» — то же соглашение, что у проверок
    -- креатива. Из него же считается молчание.
    verdict       text,      -- подтверждено | оспорено | разрешено | отказано
    reason        text,
    decided_at    timestamp,
    -- Снимок автора, а не ссылка на учётку: смена ответственного задним числом не должна
    -- переписывать, кто подтвердил объём, — под это закрываются документы.
    decided_by    text,
    decided_email text
);
CREATE INDEX IF NOT EXISTS ix_pub_request_open
    ON publisher_request (publisher_id, kind) WHERE verdict IS NULL;
CREATE INDEX IF NOT EXISTS ix_pub_request_deal ON publisher_request (deal_id);

-- Три числа сверки. Здесь факт показов ВПЕРВЫЕ входит в систему: до сверки его нет
-- нигде, и у кампании есть только состояние «запущен» (владелец 28.08.2026).
--
-- Расхождение НЕ хранится — считается из двух колонок. Хранимая разница разъезжается с
-- операндами: так уже было с суммами в импорте Диадока, и по той же причине.
--
-- `their_volume` держится отдельно от нашего, хотя пока источник один и цифры совпадают
-- всегда. Пока это так, подтверждение площадки — ПОДПИСЬ, а не сверка, и ценность её
-- в том, что под закрывающие документы есть признанный объём. В день, когда у площадки
-- появится свой счётчик, менять придётся данные, а не схему.
CREATE TABLE IF NOT EXISTS publisher_recon (
    request_id    integer PRIMARY KEY REFERENCES publisher_request(id) ON DELETE CASCADE,
    our_volume    bigint,
    their_volume  bigint,
    agreed_volume bigint
);

-- Родословная продления. Без неё «эта РК — продление той» знает только человек.
-- Исходная кампания при этом живёт своей жизнью в рамках стадий (владелец): копия —
-- экономия времени, а не перевод старой сделки в особое состояние.
ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS prolonged_from_id integer
    REFERENCES sales_deals(id);
CREATE INDEX IF NOT EXISTS ix_sales_deals_prolonged_from
    ON sales_deals (prolonged_from_id);
