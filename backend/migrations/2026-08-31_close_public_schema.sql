-- Схема `public` закрывается от роли `cabinet` по-настоящему.
--
-- В `2026-08-28_publisher_cabinet.sql` записано «REVOKE ALL ON SCHEMA public FROM cabinet»
-- и комментарий, что схема закрыта на уровне USAGE. Замер 31.08.2026 показал, что это не
-- так:
--
--     has_schema_privilege('cabinet','public','USAGE')  = true
--     has_schema_privilege('cabinet','public','CREATE') = true
--     ACL схемы: finance_user=UC/finance_user | =UC/finance_user
--
-- Пустая левая часть во второй записи — псевдороль `PUBLIC`: USAGE и CREATE выданы ВСЕМ,
-- и `REVOKE … FROM cabinet` этого не снимает, потому что права у роли не свои, а
-- унаследованные от PUBLIC. Контур на практике держался — но держался на отсутствии
-- табличных грантов (`has_table_privilege('cabinet','sales_deals','SELECT') = false`), а
-- не на том, что написано в файле. Роль при этом могла СОЗДАВАТЬ объекты в `public`.
--
-- Разница не теоретическая. «Нет гранта на таблицу» — это про сегодняшний список таблиц,
-- а ядро заводит новые при каждом старте (`create_all`). Закрытая схема защищает и от
-- завтрашних.
--
-- ── Почему REVOKE FROM PUBLIC здесь безопасен ────────────────────────────────
--
-- Ролей в кластере ровно две: `finance_user` (суперпользователь, права которого проверкой
-- вообще не ограничены, плюс у него собственный явный грант `finance_user=UC`) и
-- `cabinet`. То есть отзыв у PUBLIC задевает ровно одну роль — ту, ради которой он и
-- делается. Для PostgreSQL 15+ это к тому же поведение по умолчанию: там PUBLIC больше не
-- получает CREATE на `public` при создании базы.
--
-- Перед накатом на прод сверить состав ролей — если там появилась третья, читающая
-- `public` без явного гранта, она это заметит:
--     SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg\_%';
--
-- Повторно накатываемая: REVOKE идемпотентен.

REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Явный грант владельцу базы — чтобы отзыв у PUBLIC не зависел от того, суперпользователь
-- он сегодня или нет.
GRANT ALL ON SCHEMA public TO finance_user;

DO $$
BEGIN
    RAISE NOTICE 'cabinet: USAGE на public = %, CREATE = %, SELECT на sales_deals = %',
        has_schema_privilege('cabinet', 'public', 'USAGE'),
        has_schema_privilege('cabinet', 'public', 'CREATE'),
        has_table_privilege('cabinet', 'sales_deals', 'SELECT');
    IF has_schema_privilege('cabinet', 'public', 'USAGE') THEN
        RAISE WARNING 'схема public всё ещё видна роли cabinet — проверьте, откуда у неё право';
    END IF;
END $$;
