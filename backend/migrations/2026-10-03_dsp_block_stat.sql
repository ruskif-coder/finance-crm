-- Суточные показы блока по умолчанию площадки («Block SIMB») из админ-кабинета DSP
-- (владелец 03.10.2026, страница «Трафики → Статистика»).
--
-- Блок DSP цепляет к каждому нашему креативу сам, по кампаниям админка его не делит
-- (`platform.getStatistics` группирует только по сайту и блоку). Поэтому храним сутки по
-- блоку, а долю РК считаем по её суточным показам на площадке. Факт системы не меняется —
-- это отдельный замер, вычитается только при показе «базы».
CREATE TABLE IF NOT EXISTS dsp_block_stat (
    id           serial PRIMARY KEY,
    date         date        NOT NULL,                 -- день замера (как его отдаёт админка)
    ms_block_id  text        NOT NULL,                 -- id блока в DSP
    publisher_id integer     REFERENCES sales_publishers(id) ON DELETE SET NULL,
    surface      text,                                 -- web / app — у поверхности свой блок
    shows        integer     NOT NULL DEFAULT 0,
    clicks       integer     NOT NULL DEFAULT 0,
    fetched_at   timestamp   NOT NULL DEFAULT now(),   -- когда снято (досчёт перезаписывает)
    CONSTRAINT uq_dsp_block_stat UNIQUE (date, ms_block_id)
);
CREATE INDEX IF NOT EXISTS ix_dsp_block_stat_pub_date ON dsp_block_stat (publisher_id, date);
