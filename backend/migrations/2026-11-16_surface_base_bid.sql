-- Базовая ставка площадки в DSP (владелец 16.11.2026): у всех 100, у Купера (приложение) 161. Своя у web и app.
-- В DSP ставка источника общая на кампанию (web или app), а приложения в одной РК делят источник app — поэтому ставка
-- площадки уходит КОЭФФИЦИЕНТОМ на её блоках в таргетинге креатива: bid_rate = базовая ставка / ставка источника.
ALTER TABLE sales_publisher_surfaces ADD COLUMN IF NOT EXISTS base_bid NUMERIC(10,2) NOT NULL DEFAULT 100;
-- Купер, приложение: 161. Только если ещё стоит умолчание — повторный накат не затирает ручную правку.
UPDATE sales_publisher_surfaces SET base_bid = 161
 WHERE kind = 'app' AND base_bid = 100
   AND publisher_id IN (SELECT id FROM sales_publishers WHERE domain = 'kuper.ru');
