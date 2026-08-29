-- Кабинет как ОРГАНИЗАЦИЯ. Состав согласован владельцем 28.08.2026.
-- Продолжение 2026-08-28_publisher_cabinet.sql.
--
-- Было два уровня — человек ↔ площадки напрямую. Стало три: кабинет → площадки + люди.
-- Разница не в словах: в реестре есть настоящие сети (ИРИС — 5 площадок, ХФ — 4,
-- ЭРКА ФАРМ — 4). При двух людях в сети список площадок пришлось бы отмечать каждому
-- руками, и после первой же новой площадки эти списки разъехались бы — одному добавили,
-- второму забыли. Теперь площадка прикрепляется к кабинету один раз.

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. Кабинет
CREATE TABLE IF NOT EXISTS cabinet (
    id         serial PRIMARY KEY,
    name       text NOT NULL,
    -- `служебный` — НАШ кабинет: видит все площадки и связей не хранит. Отдельный вид,
    -- а не «кабинет со всеми площадками в связке», по простой причине: связка со всеми
    -- 41 заняла бы каждую площадку и настоящие кабинеты собрать стало бы нельзя —
    -- площадка живёт ровно в одном (см. ключ `cabinet_publisher`).
    kind       text NOT NULL DEFAULT 'площадка',   -- площадка | служебный
    -- Состояние кабинета ЦЕЛИКОМ. Отключать по одному человеку — способ забыть третьего.
    -- `черновик` — площадки прикрепили, людей ещё нет; в этом виде вход невозможен.
    state      text NOT NULL DEFAULT 'черновик',   -- черновик | активен | приостановлен
    -- Наш ответственный: у площадки вопрос — кому писать, и обратно.
    manager_id integer REFERENCES sales_reps(id),
    note       text,
    created_at timestamp DEFAULT now(),
    updated_at timestamp
);

-- Площадка ровно в ОДНОМ кабинете (владелец, 28.08.2026). Ключ по `publisher_id`, а не
-- по паре: пара разрешила бы одну площадку в двух кабинетах, задание появилось бы у
-- обоих, двое бы ответили, и второй получил бы «вердикт уже выставлен» — со стороны это
-- выглядит поломкой, а не правилом.
CREATE TABLE IF NOT EXISTS cabinet_publisher (
    publisher_id integer PRIMARY KEY REFERENCES sales_publishers(id) ON DELETE RESTRICT,
    cabinet_id   integer NOT NULL REFERENCES cabinet(id) ON DELETE CASCADE,
    added_at     timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cabinet_publisher_cabinet
    ON cabinet_publisher (cabinet_id);

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. Учётка принадлежит кабинету и растёт из КОНТАКТА площадки
--
-- Люди со стороны площадки уже заведены: `sales_publisher_contacts` — 48 контактов на
-- 26 площадках, у 36 есть почта (замер 28.08.2026). Заводя их второй раз, мы получаем
-- две записи об одном человеке: уволился — правь в двух местах, и одна обязательно
-- останется. Поэтому доступ выдаётся КОНТАКТУ (владелец: «да, внутри площадки»).
ALTER TABLE cabinet_account ADD COLUMN IF NOT EXISTS cabinet_id integer REFERENCES cabinet(id);
ALTER TABLE cabinet_account ADD COLUMN IF NOT EXISTS contact_id integer
    REFERENCES sales_publisher_contacts(id) ON DELETE SET NULL;
-- Роль внутри кабинета (владелец: нужна). Технический специалист смотрит баннер,
-- коммерческий отвечает за размещение. Без этого любой заведённый человек закрывает
-- пару и запускает выпуск ЕРИД.
ALTER TABLE cabinet_account ADD COLUMN IF NOT EXISTS can_approve boolean NOT NULL DEFAULT true;

-- `cabinet_account_publisher` НЕ удаляется — замораживается, как принято в проекте.
-- Читать её перестаём: два ответа на вопрос «чьи это площадки» однажды разойдутся,
-- а видимость теперь считается от кабинета.

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. Служебный кабинет и перенос тестовой учётки
DO $$
DECLARE c_id integer;
BEGIN
    SELECT id INTO c_id FROM cabinet WHERE kind = 'служебный' LIMIT 1;
    IF c_id IS NULL THEN
        INSERT INTO cabinet (name, kind, state, note)
        VALUES ('Служебный доступ (все площадки)', 'служебный', 'активен',
                'Наш кабинет для проверки. Видит все площадки и связей не хранит. '
                'Перед боем отключается состоянием, а не удалением: его вердикты '
                'останутся в истории.')
        RETURNING id INTO c_id;
    END IF;
    UPDATE cabinet_account SET cabinet_id = c_id WHERE cabinet_id IS NULL;
END $$;

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. Контракт: видимость считается от КАБИНЕТА
--
-- Приостановленный кабинет перестаёт видеть задания сразу, не дожидаясь, пока истекут
-- выданные токены: проверка на каждом запросе, а не только при входе.
CREATE OR REPLACE VIEW pub.account_publisher_v1 AS
SELECT a.id AS account_id, p.id AS publisher_id, p.name, p.domain, p.code
FROM cabinet_account a
JOIN cabinet c ON c.id = a.cabinet_id
JOIN sales_publishers p ON (
        c.kind = 'служебный'
     OR EXISTS (SELECT 1 FROM cabinet_publisher cp
                WHERE cp.cabinet_id = c.id AND cp.publisher_id = p.id))
WHERE c.state = 'активен';

-- Право согласовывать кабинет проверяет сам: ядро о ролях внешнего контура не знает и
-- знать не должно — у него своя матрица прав, к этой отношения не имеющая.
CREATE OR REPLACE VIEW pub.account_v1 AS
SELECT a.id, a.email, a.name, a.hashed_password, a.is_active, a.can_approve
FROM cabinet_account a;

GRANT SELECT ON pub.account_v1, pub.account_publisher_v1 TO cabinet;
