-- Решение по пикселю Weborama: «надо / не надо» — и отдельно «решали ли вообще».
--
-- Согласовано с владельцем 18.09.2026. Колонка `weborama_pixel` булева и NOT NULL, то
-- есть «не надо» и «ещё не решали» в ней неразличимы. Блоку «Доп. параметры РК» на
-- карточке сделки это и нужно различать: он должен стоять развёрнутым, пока выбор не
-- сделан, и сворачиваться после.
--
-- Выбран вариант с ОТДЕЛЬНОЙ КОЛОНКОЙ, а не nullable-флагом: существующее поле не
-- меняет смысла, 948 живых сделок автоматически читаются как «не выбрано», и ни один
-- запрос вида `weborama_pixel = false` не начинает означать другое. Заодно видно, когда
-- решение приняли.
--
-- Повторный накат безопасен.

ALTER TABLE sales_deals
    ADD COLUMN IF NOT EXISTS weborama_pixel_decided_at timestamp without time zone;

COMMENT ON COLUMN sales_deals.weborama_pixel_decided_at IS
    'Когда по сделке приняли решение о пикселе Weborama. NULL — выбор ещё не сделан, '
    'блок доп. параметров РК на карточке стоит развёрнутым.';

-- Уже заказанный пиксель — это состоявшийся выбор: время берём из момента заказа.
UPDATE sales_deals
   SET weborama_pixel_decided_at = weborama_pixel_at
 WHERE weborama_pixel IS TRUE
   AND weborama_pixel_at IS NOT NULL
   AND weborama_pixel_decided_at IS NULL;
