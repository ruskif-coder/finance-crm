-- Доступность сайтов площадок (владелец 30.09.2026) — перенос внешнего скрипта downbot.py
-- в систему: раз в час проверяем, открываются ли сайты, тревога трафик-админу и менеджеру
-- паблишеров, вкладка в админке трафика, алерт в конвейере согласования.
--
-- Повторный накат ничего не меняет.

-- 1. Как проверять сайт поверхности: обычным запросом, настоящим браузером (сайты с
--    антиботом, которые режут простой запрос) или не проверять вовсе.
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS site_check varchar(8)
    NOT NULL DEFAULT 'http';
COMMENT ON COLUMN sales_publisher_surfaces.site_check IS
  'Проверка доступности сайта: http — обычный запрос, browser — через браузер (антибот), off — не проверять';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_surface_site_check') THEN
    ALTER TABLE sales_publisher_surfaces ADD CONSTRAINT ck_surface_site_check
      CHECK (site_check IN ('http', 'browser', 'off'));
  END IF;
END $$;
-- Как было в конфиге скрипта: эти сайты режут простой запрос.
UPDATE sales_publisher_surfaces s SET site_check = 'browser'
  FROM sales_publishers p
 WHERE p.id = s.publisher_id AND s.kind = 'web' AND s.site_check = 'http'
   AND lower(p.domain) IN ('zdesapteka.ru', 'aptekabv.ru');

-- 2. История проверок. Строка на проверку одного адреса; текущее состояние — последняя
--    строка адреса. Площадка пустая у доп. сайтов вне реестра. Хранится 30 дней.
CREATE TABLE IF NOT EXISTS site_checks (
    id           bigserial PRIMARY KEY,
    url          text        NOT NULL,
    publisher_id integer     REFERENCES sales_publishers(id) ON DELETE CASCADE,
    checked_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    status       varchar(20) NOT NULL,   -- ok | antibot | down
    http_status  integer,
    method       varchar(12),            -- http | browser
    final_url    text,
    message      text
);
COMMENT ON TABLE site_checks IS
  'Проверки доступности сайтов площадок: статус ok | antibot | down, способ, код ответа, ошибка';
CREATE INDEX IF NOT EXISTS ix_site_checks_url_time ON site_checks (url, checked_at DESC);
-- Точное время каждой вставки, а не начало транзакции: иначе проверки одного прогона
-- получают одинаковое время и «последняя» выбирается случайно.
ALTER TABLE site_checks ALTER COLUMN checked_at SET DEFAULT clock_timestamp();

-- 3. Настройки: доп. сайты вне реестра (строка — адрес и, через пробел, режим browser),
--    исключения для «пропали из показов DSP». Значения — из конфига скрипта; dialog.ru
--    не включён: площадка в архиве, а проверяем только не архивные (владелец 30.09.2026).
INSERT INTO company_settings (key, value) VALUES
  ('site_monitor_extra', E'https://vitaexpress.ru browser\nhttps://asna.ru browser\nhttps://apteka-april.ru\nhttps://gastronom.ru\nhttps://tanukifamily.ru browser\nhttps://igroray.ru\nhttps://mirf.ru\nhttps://magnit.ru'),
  ('site_monitor_dsp_exclude', E'adfox.ru\ncreampy.ru')
ON CONFLICT (key) DO NOTHING;
