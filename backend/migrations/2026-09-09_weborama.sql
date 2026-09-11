-- Контур Weborama (WCM): реестр соответствий, журнал попыток и пиксель на площадке РК.
-- Согласовано с владельцем 09.09.2026.
--
-- ЗАЧЕМ РЕЕСТР. У Weborama нет идемпотентности: повторный вызов заведёт вторую вставку, а
-- удалить или переименовать её по API нечем. Значит уникальность обеспечиваем МЫ, и
-- обеспечиваем её ограничением в базе, а не проверкой в коде: проверка в коде не спасает
-- от двух одновременных нажатий, а ограничение спасает. Второй счётчик на одной площадке
-- разделил бы её показы пополам, и оба числа были бы неверны.
--
-- ЧЕГО ЗДЕСЬ НЕТ И ПОЧЕМУ. Хеши DSP не заводим: `ad_campaign.ms_campaign_xxhash` и
-- `ad_campaign_creative.ms_creative_xxhash` уже есть и уже показываются в кабинете
-- трафика — состояние DSP вычисляется из них, второе хранилище того же факта разошлось
-- бы с первым.

-- ── 1. Соответствие наших сущностей их идентификаторам ──────────────────────
CREATE TABLE IF NOT EXISTS weborama_refs (
    id          SERIAL PRIMARY KEY,
    -- Аккаунт WCM: Weborama выдаёт их списком и закрепляет за клиентами. Часть ключа, а
    -- не справочная колонка: одна и та же наша сделка в другом аккаунте — другая запись.
    account_id  VARCHAR(32)  NOT NULL,
    -- project | campaign | insertion
    kind        VARCHAR(16)  NOT NULL,
    -- Наш id: сделка для проекта, РК для кампании, площадка РК для вставки. БЕЗ внешнего
    -- ключа намеренно — указывает в разные таблицы в зависимости от `kind`, как
    -- `ord_submissions.local_id`.
    local_id    INTEGER      NOT NULL,
    wcm_id      VARCHAR(32)  NOT NULL,
    -- Имя, под которым завели. Переименовать в их кабинете нельзя, поэтому имя — часть
    -- факта: по нему сверяют строку в отчёте Weborama с нашей площадкой.
    label       VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT now(),
    created_by  INTEGER      REFERENCES users(id)
);

-- ГЛАВНОЕ ограничение файла: одна наша сущность заводится в одном аккаунте ровно раз.
-- Именно оно делает повтор безопасным и позволяет когда-нибудь включить автоматику.
CREATE UNIQUE INDEX IF NOT EXISTS uq_weborama_ref
    ON weborama_refs (account_id, kind, local_id);
CREATE INDEX IF NOT EXISTS ix_weborama_ref_wcm ON weborama_refs (wcm_id);

COMMENT ON TABLE weborama_refs IS
  'Наши сущности → идентификаторы в WCM. Уникальность (аккаунт, вид, наш id) — защита от дублей в чужой системе.';

-- ⚠ ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ. Одна площадка = одна вставка. Если окажется, что для DSP нужны
-- ОБЕ вставки (формат 3 под поле `pixel` и формат 4 под `js_code_audit`), потребуется
-- отдельная миграция: в ключ добавится вид формата. Вопрос Weborama задан, ответа нет, и
-- закладываться на неизвестное здесь дороже, чем потом дописать колонку.

-- ── 2. Журнал попыток ───────────────────────────────────────────────────────
-- Строка пишется и КОММИТИТСЯ ДО запроса, а не после ответа. Заведение в чужой системе
-- необратимо, а ответ может потеряться по таймауту: без следа «попытка началась» повтор
-- создаёт дубль, который уже не отозвать. Тот же порядок, что в `ord_submissions`.
CREATE TABLE IF NOT EXISTS weborama_submissions (
    id           BIGSERIAL PRIMARY KEY,
    account_id   VARCHAR(32) NOT NULL,
    kind         VARCHAR(16) NOT NULL,      -- project | campaign | insertion | tag
    local_id     INTEGER,
    method       VARCHAR(96) NOT NULL,      -- путь их метода
    request      JSONB,                     -- тело целиком: их отказ указывает на поле,
                                            -- а собирается отправка из нескольких мест
    started_at   TIMESTAMP   NOT NULL DEFAULT now(),
    finished_at  TIMESTAMP,                 -- NULL = исход неизвестен, повтор запрещён
    http_status  INTEGER,
    wcm_id       VARCHAR(32),
    error        TEXT,
    user_id      INTEGER     REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_weborama_sub_local
    ON weborama_submissions (kind, local_id);
-- Незавершённые ищем часто и всегда все сразу — частичный индекс дешевле полного.
CREATE INDEX IF NOT EXISTS ix_weborama_sub_open
    ON weborama_submissions (started_at) WHERE finished_at IS NULL;

COMMENT ON TABLE weborama_submissions IS
  'Журнал отправок в WCM. Строка до вызова; finished_at IS NULL = исход неизвестен, повтор руками.';

-- ── 3. Пиксель на площадке РК ───────────────────────────────────────────────
-- Хранится СЫРОЙ пиксель показа, как пришёл от них: с `[RANDOM]`, `~WIDTH~`, `${GDPR}`.
-- Итоговый тег НЕ храним — он производный и зависит от того, куда едет (макрос
-- рандомизатора у DSP и Adfox разный) и от размера конкретного креатива. Хранить
-- производное значит завести вторую правду, которая разойдётся с первой.
ALTER TABLE ad_campaign_placement
    ADD COLUMN IF NOT EXISTS weborama_pixel TEXT;

COMMENT ON COLUMN ad_campaign_placement.weborama_pixel IS
  'Сырой пиксель показа Weborama (a.A=im) как пришёл. Итоговый тег собирается на лету: макрос зависит от площадки назначения, размер — от креатива.';
