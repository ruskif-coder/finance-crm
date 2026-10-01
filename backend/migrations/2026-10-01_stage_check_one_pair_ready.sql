-- Вход в «В размещении» — по ОДНОЙ собранной площадке (владелец 01.10.2026, первый боевой
-- запуск 54ZYCH): «хоть одна площадка полностью собрана и готова к запуску — запуск и
-- перевод стадии».
--
-- Было: вход запирали веера «все из всех» — комплекты прошли проверку, ВСЕ площадки
-- согласовали, у ВСЕХ комплектов ЕРИД, РК создана в DSP. Сделка с запущенной РК стояла
-- в сборке из-за площадок, которые ещё не ответили.
--
-- Стало: запирает одна проверка `one_pair_ready` (app/sales/stage_checks.py) — есть
-- площадка, у которой комплект прошёл проверку трафика, площадка согласовала, у
-- комплекта ЕРИД и креатив выгружен в DSP (внешней — не нужно). Прежние веера остаются
-- ПОДСКАЗКАМИ: «18 из 22» видно в чек-листе, перехода не держит. `campaign_ready` тоже
-- подсказка: РК только из внешних площадок кампании в нашей DSP не имеет.
--
-- Повторный накат ничего не меняет.
UPDATE sales_stage_checks c SET is_blocking = false
  FROM sales_stages s
 WHERE s.id = c.stage_id AND s.name = 'В размещении'
   AND c.check_key IN ('creatives_accepted', 'placements_approved', 'erid_issued', 'campaign_ready')
   AND c.is_blocking;

INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, sort_order, applies_when, hint)
SELECT s.id, 'one_pair_ready', true, -1, '{"service_id": 28}'::jsonb,
       'Хотя бы одна площадка: проверена трафиком, согласована, ЕРИД, креатив в DSP'
  FROM sales_stages s
 WHERE s.name = 'В размещении'
ON CONFLICT (stage_id, check_key) DO NOTHING;

-- Дальше «В размещении» сделку двигает ТРАФИК кнопкой «Завершить РК» (владелец
-- 01.10.2026): аккаунт может добавлять баннеры, но не переводить сделку. Проверка
-- `campaign_finished` запирает вход в «Итоговую сверку» и во все стадии после неё
-- (прыжок через стадию чтит требования только цели). «Сорвалась» — не запирается.
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, sort_order, applies_when, hint)
SELECT s.id, 'campaign_finished', true, -2, '{"service_id": 28}'::jsonb,
       'Сделку дальше размещения двигает трафик кнопкой «Завершить РК»'
  FROM sales_stages s
 WHERE s.name IN ('Итоговая сверка', 'Подготовка ДС', 'Согласование ДС', 'Подготовка закрывающих',
                  'ЭДО', 'Отчёты в ОРД', 'Оплата', 'Архив успешных сделок')
ON CONFLICT (stage_id, check_key) DO NOTHING;
