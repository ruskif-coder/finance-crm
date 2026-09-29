-- Особенности площадок для трафика (владелец 27–29.09.2026, docs/ПЛАН_админка_трафиков_особенности_площадок.md).
-- Схема согласована владельцем 29.09.2026. Повторно накатываемая.

-- Как размещаемся на поверхности: dsp — наша DSP; adfox — Adfox площадки (креатив
-- заводит наш трафик); outside — вне контуров (Купер, Польза). Пусто — не задано.
-- На поверхности, а не на площадке: у Максавита web идёт через Adfox, app — через DSP.
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS placement_channel varchar(16);

-- Ссылки для app (только у app-поверхности). Пусто — как было: в <a href> макрос клика
-- DSP. web — в href веб-ссылка. both — в href диплинк; веб-ссылка всё равно нужна,
-- она уходит в url / adomain DSP (диплинк там не принимается).
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS app_links varchar(16);

-- Дополнительный код Adfox для макроса %user6% — текстом, правится в админке без выкладки.
-- Заполняется у web-поверхности с каналом adfox.
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS adfox_extra_code text;

-- Диплинк пары «креатив × площадка» — рядом с посадочной, по тем же причинам.
ALTER TABLE launch_prep_set_target ADD COLUMN IF NOT EXISTS deeplink_url varchar(1024);

DO $$ BEGIN
  ALTER TABLE sales_publisher_surfaces ADD CONSTRAINT ck_surface_channel
    CHECK (placement_channel IS NULL OR placement_channel IN ('dsp', 'adfox', 'outside'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE sales_publisher_surfaces ADD CONSTRAINT ck_surface_app_links
    CHECK (app_links IS NULL OR (kind = 'app' AND app_links IN ('web', 'both')));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── Стартовые значения (ответы владельца 29.09) — только там, где ещё пусто ──────────
-- Adfox — web трёх площадок; вне контура — Купер и Польза целиком; остальное — DSP.
UPDATE sales_publisher_surfaces s SET placement_channel = 'adfox'
  FROM sales_publishers p
 WHERE p.id = s.publisher_id AND s.kind = 'web' AND s.placement_channel IS NULL
   AND lower(p.name) IN ('aptechestvo.ru', 'maksavit.ru', 'zdesapteka.ru');
UPDATE sales_publisher_surfaces s SET placement_channel = 'outside'
  FROM sales_publishers p
 WHERE p.id = s.publisher_id AND s.placement_channel IS NULL
   AND lower(p.name) IN ('kuper', 'polza.ru');
UPDATE sales_publisher_surfaces SET placement_channel = 'dsp' WHERE placement_channel IS NULL;

-- Ссылки app: веб-ссылка в href — minicen, newapteka, apteka25, aptekabv; Максавит — диплинк.
UPDATE sales_publisher_surfaces s SET app_links = 'web'
  FROM sales_publishers p
 WHERE p.id = s.publisher_id AND s.kind = 'app' AND s.app_links IS NULL
   AND lower(p.name) IN ('minicen.ru', 'newapteka.ru', 'apteka25.ru', 'aptekabv.ru');
UPDATE sales_publisher_surfaces s SET app_links = 'both'
  FROM sales_publishers p
 WHERE p.id = s.publisher_id AND s.kind = 'app' AND s.app_links IS NULL
   AND lower(p.name) = 'maksavit.ru';

-- Доп. код Adfox: iframe площадки трижды (как прислал владелец 27.09).
UPDATE sales_publisher_surfaces s SET adfox_extra_code = repeat(
    '<iframe src="https://simbtech.ru/afcar/' || x.slug
    || '.html" style="width:1px;height:1px;position: absolute"></iframe>' || E'\n', 3)
  FROM sales_publishers p,
       (VALUES ('aptechestvo.ru', 'aptch'), ('maksavit.ru', 'mxvt'), ('zdesapteka.ru', 'zap')) AS x(name, slug)
 WHERE p.id = s.publisher_id AND lower(p.name) = x.name AND s.kind = 'web'
   AND s.adfox_extra_code IS NULL;

-- Право «Трафики · Особенности площадок» заведено в SECTIONS без бэкфилла: выдаёт владелец
-- («трафик админ»). Админ видит всё без строки в role_permissions.

SELECT p.name, s.kind, s.placement_channel, s.app_links, (s.adfox_extra_code IS NOT NULL) AS has_code
  FROM sales_publisher_surfaces s JOIN sales_publishers p ON p.id = s.publisher_id
 WHERE s.placement_channel <> 'dsp' OR s.app_links IS NOT NULL
 ORDER BY 1, 2;
