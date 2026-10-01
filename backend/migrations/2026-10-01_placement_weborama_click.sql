-- Кликовая ссылка Weborama у площадки РК (владелец 01.10.2026, схема согласована).
--
-- Weborama отдаёт в теге вставки ДВЕ ссылки: пиксель показа (`a.A=im`, хранится в
-- `weborama_pixel`) и счётчик клика (`a.A=cl`, кончается на `&g.lu=`). Кликовую мы
-- выбрасывали, и в DSP конечным URL креатива уходила голая посадочная — клики Weborama
-- не считались. Теперь хранится сырой, как пришёл (с `[RANDOM]`, `[ERID_*]`): итоговая
-- ссылка производная — макрос DSP, ЕРИД и посадочная в `g.lu` подставляются при выгрузке
-- (`dsp.provision.click_link`).
--
-- Повторный накат ничего не меняет.
ALTER TABLE ad_campaign_placement ADD COLUMN IF NOT EXISTS weborama_click text;
COMMENT ON COLUMN ad_campaign_placement.weborama_click IS
  'Сырой кликовый счётчик Weborama (a.A=cl … &g.lu=) — конечный URL креатива в DSP с посадочной в g.lu';
