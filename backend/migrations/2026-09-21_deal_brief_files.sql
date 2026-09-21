-- Файлы, приложенные к брифу сделки. Согласовано с владельцем 21.09.2026.
--
-- ЗАЧЕМ. Бриф приходит от клиента не только текстом: презентация, тз, медиаплан
-- рекламодателя. До сих пор его перепечатывали в поле, а исходник жил в почте — то
-- есть у всех, кроме того, кто открыл сделку.
--
-- ПОЧЕМУ СВОЯ ТАБЛИЦА, а не тройка колонок на sales_deals: тот же довод, что записан у
-- файлов площадки (sales_publisher_documents) — иначе каждый новый вид вложения требует
-- новых колонок. И файлов бывает несколько: презентация плюс тз — обычная пачка, а одна
-- колонка молча затирала бы первый файл вторым.
--
-- ИМЯ НА ДИСКЕ И ИМЯ ЧЕЛОВЕКА РАЗДЕЛЕНЫ. На диск кладётся санитизированное имя с
-- префиксом id (два «бриф.pdf» иначе затрут друг друга), скачивается файл под своим —
-- как у договоров.
CREATE TABLE IF NOT EXISTS sales_deal_brief_files (
    id            SERIAL PRIMARY KEY,
    deal_id       INTEGER NOT NULL REFERENCES sales_deals(id) ON DELETE CASCADE,
    filename      VARCHAR(255) NOT NULL,   -- имя на диске, /app/uploads/deal_briefs/
    original_name VARCHAR(255) NOT NULL,   -- под ним файл отдаётся человеку
    size_bytes    INTEGER,
    uploaded_at   TIMESTAMP NOT NULL DEFAULT now(),
    uploaded_by   INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_deal_brief_files_deal ON sales_deal_brief_files (deal_id);
