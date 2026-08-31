-- Все представления схемы `pub` — барьеры безопасности.
--
-- `security_barrier` запрещает планировщику протаскивать пользовательское условие ПОД
-- собственный фильтр представления. Без него запрос вида «покажи задания, где …» может
-- быть исполнен так, что чужая строка сперва проверяется условием пользователя и только
-- потом отсекается фильтром `pub.allowed_publisher_ids()`. Сама строка наружу не попадёт,
-- но по времени ответа или по тексту ошибки (деление на ноль, приведение типа) внешняя
-- сторона узнаёт, что она существует. Для внешнего контура, где по ту сторону не наш
-- сотрудник, это разница между «не отдаём» и «не отдаём и не подтверждаем».
--
-- ── Как опция потерялась ─────────────────────────────────────────────────────
--
-- Замер 31.08.2026 перед выкладкой: из 13 представлений `pub` опция стояла у четырёх
-- (`document_v1`, `done_v1`, `mute_v1`, `task_file_v1`). У `task_v1` и `profile_v1` она
-- БЫЛА и слетела 30.08: миграции `_task_surface` и `_team_from_our_contacts` переписали
-- их через `CREATE OR REPLACE VIEW`, а он сбрасывает `reloptions` — переставить забыли.
-- Остальные семь не имели её никогда.
--
-- Это тихая потеря: представление работает, состав колонок прежний, приборы зелёные.
-- Поэтому здесь не только правка, но и прибор — `tests/test_cabinet_contract.py`
-- проверяет опцию у КАЖДОГО представления схемы, и следующий `CREATE OR REPLACE` без неё
-- покраснеет.
--
-- Ставим на все 13 разом, а не только на потерявшие: «каждое представление `pub` —
-- барьер» это правило контура, а список исключений через месяц никто не вспомнит.
-- Цена — запрет на протаскивание условий внутрь; на таблицах этого контура (десятки и
-- сотни строк) она неразличима.
--
-- Повторно накатываемая: `ALTER VIEW … SET` идемпотентен по устройству.

DO $$
DECLARE
    v record;
BEGIN
    FOR v IN
        SELECT c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'pub' AND c.relkind = 'v'
         ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER VIEW pub.%I SET (security_barrier = true)', v.relname);
    END LOOP;
END $$;

-- Сводка — чтобы накатывающий видел результат, а не отсутствие ошибки.
DO $$
DECLARE
    total integer;
    guarded integer;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE 'security_barrier=true' = ANY(c.reloptions))
      INTO total, guarded
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'pub' AND c.relkind = 'v';
    RAISE NOTICE 'представлений pub: % · с security_barrier: %', total, guarded;
    IF total <> guarded THEN
        RAISE WARNING 'не у всех представлений выставлен барьер';
    END IF;
END $$;
