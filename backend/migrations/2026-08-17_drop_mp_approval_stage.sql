-- Убираем стадию «МП согласование» (Песочница): признана бюрократией владельцем 2026-08-17.
-- Стартовых стадий остаётся две: «МП Подготовка» (готовится) и «МП Отправлено».
--
-- Побочный эффект, ради которого это стоило сделать и без просьбы: стадия делила
-- битрикс-привязку UC_ZLUZT8 с «МП Отправлено», а резолвер (app/sales/stage_resolve.py)
-- при двойнике берёт первую по (этап.sort_order, стадия.sort_order) — то есть всё,
-- что приезжало из Битрикса на эту пару, садилось на «МП согласование». Теперь пара
-- однозначна и ведёт на «МП Отправлено».
--
-- Удаление строки, а не флаг «неактивна»: на стадии нет ни одной сделки и ни одной
-- записи истории, ссылаться на неё нечему. Пустая строка каталога — не первичные данные,
-- терять нечего; повторный сев её не вернёт (seed_stage_catalog полностью сеет только
-- пустой каталог), из CATALOG она тоже убрана.

BEGIN;

-- Предохранитель: если на стадии всё-таки появились сделки или история — не удаляем,
-- а падаем. Молча перевесить чужие сделки на соседнюю стадию нельзя: это движение
-- сделки, оно должно быть видимым и с автором.
DO $$
DECLARE
    sid integer;
    n_deals integer;
    n_hist integer;
BEGIN
    SELECT s.id INTO sid FROM sales_stages s
      JOIN sales_stage_phases p ON p.id = s.phase_id
     WHERE p.sort_order = 0 AND s.name = 'МП согласование';
    IF sid IS NULL THEN
        RAISE NOTICE 'Стадия «МП согласование» уже отсутствует — пропуск';
        RETURN;
    END IF;

    SELECT count(*) INTO n_deals FROM sales_deals WHERE our_stage_id = sid;
    SELECT count(*) INTO n_hist FROM sales_deal_stage_history
     WHERE to_stage_id = sid OR from_stage_id = sid;
    IF n_deals > 0 OR n_hist > 0 THEN
        RAISE EXCEPTION 'На стадии % сделок и % записей истории — перенесите их движением, потом удаляйте', n_deals, n_hist;
    END IF;

    DELETE FROM sales_stages WHERE id = sid;
    RAISE NOTICE 'Стадия «МП согласование» (id=%) удалена', sid;
END $$;

-- Порядок в этапе делаем плотным: «МП Отправлено» встаёт второй, терминальная — последней.
UPDATE sales_stages s SET sort_order = 1
  FROM sales_stage_phases p WHERE p.id = s.phase_id AND p.sort_order = 0 AND s.name = 'МП Отправлено';
UPDATE sales_stages s SET sort_order = 2
  FROM sales_stage_phases p WHERE p.id = s.phase_id AND p.sort_order = 0 AND s.name = 'Сделка не случилась';

COMMIT;
