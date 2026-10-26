-- Сверка паблишера (владелец 12.10 и 26.10.2026; план docs/ПЛАН_сверка_паблишера.md, схема согласована 26.10).
-- Строка сверки = площадка × отчётный месяц. Повторно накатываемая.
--
--   1. publisher_request / publisher_recon (28.08, на проде ни одной строки) — дополнены под сверку;
--   2. переписка, вложения и разнесение итога по размещениям — новые таблицы;
--   3. факт площадки — ОДНО представление `publisher_placement_v`: из него читают и кабинет (`pub.campaign_v1` —
--      фильтр по своим площадкам), и экран менеджера. Две копии формулы (Block SIMB, источники) разошлись бы;
--   4. представления кабинета для сверки;
--   5. право «Паблишеры · Взаимодействие» + бэкфилл менеджеру паблишеров.

-- ── 1. заголовок сверки и три цифры ─────────────────────────────────────────────────────────────
ALTER TABLE publisher_request ADD COLUMN IF NOT EXISTS sent_by text;           -- кто отправил площадке (снимок имени)
ALTER TABLE publisher_request ADD COLUMN IF NOT EXISTS pub_seen_at timestamp;  -- площадка последний раз открыла переписку
ALTER TABLE publisher_request ADD COLUMN IF NOT EXISTS our_seen_at timestamp;  -- менеджер последний раз открыл переписку
-- Одна сверка на площадку и месяц: повторный ответ — сообщение в ту же переписку, а не новая сверка.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pub_request_recon ON publisher_request (publisher_id, period) WHERE kind = 'сверка';

-- CPM договора на момент согласования: смена CPM в договоре потом не двигает деньги закрытого месяца.
ALTER TABLE publisher_recon ADD COLUMN IF NOT EXISTS cpm numeric(12,2);

-- ── 2. переписка, вложения, разнесение итога ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS publisher_request_message (
    id           serial PRIMARY KEY,
    request_id   integer NOT NULL REFERENCES publisher_request(id) ON DELETE CASCADE,
    -- чей ход, решает последнее НЕсистемное сообщение: «площадка» — есть ответ (ход наш), «мы» — ожидает
    side         text NOT NULL CHECK (side IN ('площадка', 'мы', 'система')),
    author_name  text,                     -- снимок автора: людей за площадкой несколько
    author_email text,
    body         text,
    volume       bigint CHECK (volume IS NULL OR volume >= 0),   -- предложенная цифра показов за месяц
    created_at   timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pub_request_message ON publisher_request_message (request_id, id);

CREATE TABLE IF NOT EXISTS publisher_request_file (
    id            serial PRIMARY KEY,
    message_id    integer NOT NULL REFERENCES publisher_request_message(id) ON DELETE CASCADE,
    path          text NOT NULL,           -- путь в томе загрузок, как у launch_prep_pair_file
    original_name text,
    content_type  text,
    size_bytes    integer,
    uploaded_at   timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pub_request_file ON publisher_request_file (message_id);

-- Итог месяца, разнесённый по размещениям площадки (сделка × площадка, `launch_prep_target`) пропорционально
-- их доле нашего факта: отсюда себестоимость сделок и итог в ОРД по ЕРИД. Заполняется при согласовании.
CREATE TABLE IF NOT EXISTS publisher_recon_line (
    request_id    integer NOT NULL REFERENCES publisher_request(id) ON DELETE CASCADE,
    target_id     integer NOT NULL REFERENCES launch_prep_target(id) ON DELETE CASCADE,
    our_volume    bigint NOT NULL,
    agreed_volume bigint NOT NULL,
    PRIMARY KEY (request_id, target_id)
);

-- ── 3. факт площадки — одно представление ───────────────────────────────────────────────────────
-- Тело — живое определение pub.campaign_v1 (после 2026-10-19_pub_fact_prio.sql) БЕЗ фильтра по своим площадкам.
CREATE OR REPLACE VIEW publisher_placement_v AS
 SELECT t.id AS placement_id,
    t.publisher_id,
    pb.domain AS site,
    COALESCE(adv.short_name, adv.name, '—'::character varying)::text || COALESCE(' · '::text || NULLIF(br.name::text, ''::text), ''::text) AS brand,
    d.product AS service,
    t.surface_kind AS surface,
    COALESCE(t.period_from, d.period_from) AS date_from,
    COALESCE(t.period_to, d.period_to) AS date_to,
    COALESCE(pl.plan_show, 0::double precision)::bigint AS plan,
    COALESCE(st.shows, 0::numeric)::bigint AS fact,
    COALESCE(pb.cpm_contract, 0::double precision)::numeric AS cpm,
    COALESCE(er.erid, ''::character varying) AS erid,
        CASE
            WHEN rej.pair_id IS NOT NULL THEN 'отказ'::text
            WHEN "dec".declined AND NOT "dec".live THEN 'отказ'::text
            WHEN t.state::text = 'отказ площадки'::text THEN 'отказ'::text
            WHEN pl.status::text = 'запущен'::text THEN 'в размещении'::text
            WHEN pl.status::text = 'пауза'::text THEN 'пауза'::text
            WHEN pl.status::text = 'завершена'::text THEN 'завершён'::text
            WHEN c.status::text = 'запущена'::text THEN 'в размещении'::text
            WHEN c.status::text = ANY (ARRAY['пауза'::character varying::text, 'остановлена'::character varying::text]) THEN 'пауза'::text
            WHEN c.status::text = 'окончена'::text THEN 'завершён'::text
            WHEN COALESCE(t.period_to, d.period_to) < CURRENT_DATE THEN 'завершён'::text
            WHEN t.state::text = ANY (ARRAY['завершён'::character varying::text, 'сверка завершена'::character varying::text, 'архив'::character varying::text]) THEN 'завершён'::text
            WHEN t.state::text = ANY (ARRAY['согласован'::character varying::text, 'ерид получен'::character varying::text, 'заведён в DSP'::character varying::text, 'в размещении'::character varying::text]) THEN 'ждёт старта'::text
            ELSE 'ждёт согласования'::text
        END AS status,
    (EXISTS ( SELECT 1
           FROM publisher_request pr
          WHERE pr.kind = 'сверка'::text AND pr.verdict IS NOT NULL AND pr.publisher_id = t.publisher_id AND (pr.deal_id IS NULL OR pr.deal_id = t.deal_id) AND pr.period = to_char(COALESCE(t.period_from, d.period_from)::timestamp with time zone, 'YYYY-MM'::text))) AS reconciled
   FROM launch_prep_target t
     JOIN sales_publishers pb ON pb.id = t.publisher_id
     JOIN sales_deals d ON d.id = t.deal_id
     LEFT JOIN sales_advertisers adv ON adv.id = d.advertiser_id
     LEFT JOIN sales_brands br ON br.id = d.brand_id
     LEFT JOIN ad_campaign c ON c.deal_id = d.id
     LEFT JOIN ad_campaign_placement pl ON pl.campaign_id = c.id AND pl.publisher_id = t.publisher_id
     LEFT JOIN LATERAL ( SELECT sum(dd.own) - round(COALESCE(sum(
                CASE
                    WHEN tt.tot > 0 AND kb.k > 0 THEN LEAST(dd.dsp::numeric, kb.k::numeric * dd.dsp::numeric / tt.tot::numeric)
                    ELSE 0::numeric
                END), 0::numeric)) AS shows
           FROM ( SELECT s.date,
                    sum(s.shows) AS own,
                    COALESCE(sum(s.shows) FILTER (WHERE s.source::text <> ALL (ARRAY['adfox'::text, 'prio'::text])), 0::bigint) AS dsp
                   FROM ad_campaign_stat s
                  WHERE s.campaign_id = c.id AND s.placement_id = pl.id AND (s.source::text = ANY (ARRAY['adfox'::character varying::text, 'demo'::character varying::text, 'dsp'::character varying::text, 'manual'::character varying::text, 'ms'::character varying::text, 'prio'::character varying::text]))
                  GROUP BY s.date) dd
             LEFT JOIN LATERAL ( SELECT sum(b.shows) AS k
                   FROM dsp_block_stat b
                  WHERE b.publisher_id = t.publisher_id AND b.date = dd.date) kb ON true
             LEFT JOIN LATERAL ( SELECT sum(s2.shows) AS tot
                   FROM ad_campaign_stat s2
                     JOIN ad_campaign_placement p2 ON p2.id = s2.placement_id
                  WHERE p2.publisher_id = t.publisher_id AND s2.date = dd.date AND (s2.source::text = ANY (ARRAY['demo'::character varying::text, 'dsp'::character varying::text, 'manual'::character varying::text, 'ms'::character varying::text]))) tt ON true) st ON true
     LEFT JOIN LATERAL ( SELECT cs.erid
           FROM launch_prep_creative_set cs
             LEFT JOIN launch_prep_pair p2 ON p2.set_id = cs.id AND p2.target_id = t.id
          WHERE cs.deal_id = t.deal_id AND COALESCE(TRIM(BOTH FROM cs.erid), ''::text) <> ''::text AND (COALESCE(cs.erid_source, 'наш'::character varying)::text <> 'наш'::text OR (cs.ord_status::text = ANY (ARRAY['Active'::character varying::text, 'Registering'::character varying::text]))) AND (p2.id IS NOT NULL OR cs.publisher_id = t.publisher_id)
          ORDER BY (p2.id IS NOT NULL) DESC, cs.no DESC
         LIMIT 1) er ON true
     LEFT JOIN LATERAL ( SELECT p.id AS pair_id
           FROM launch_prep_pair p
             JOIN launch_prep_review r ON r.pair_id = p.id
          WHERE p.target_id = t.id AND r.verdict::text = 'отказ'::text
            -- Отказ — только если у площадки нет живого согласованного креатива: с 21.10.2026 отказ не запирает новый
            -- креатив, и площадка, отказавшая по старому и открутившая новый, не «отказ» (иначе её показы выпали бы из сверки).
            AND NOT EXISTS (SELECT 1 FROM launch_prep_pair p3
                             WHERE p3.target_id = t.id AND p3.agreed_at IS NOT NULL AND p3.withdrawn_at IS NULL)
         LIMIT 1) rej ON true
     LEFT JOIN LATERAL ( SELECT bool_or(p.withdraw_kind::text = 'отказ в правках'::text) AS declined,
            bool_or(p.withdrawn_at IS NULL AND p.sent_at IS NOT NULL) AS live
           FROM launch_prep_pair p
          WHERE p.target_id = t.id) "dec" ON true
  WHERE t.archived_at IS NULL AND (EXISTS ( SELECT 1
           FROM launch_prep_pair p
             JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind::text = 'площадка'::text
          WHERE p.target_id = t.id AND r.verdict IS NOT NULL AND (p.withdrawn_at IS NULL OR p.withdraw_kind::text = 'отказ в правках'::text)));

CREATE OR REPLACE VIEW pub.campaign_v1 WITH (security_barrier) AS
SELECT placement_id, publisher_id, site, brand, service, surface, date_from, date_to, plan, fact, cpm, erid, status, reconciled
  FROM publisher_placement_v
 WHERE publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.campaign_v1 TO cabinet;

-- ── 4. кабинет: сверки своих площадок ───────────────────────────────────────────────────────────
-- `offer` — цифра, которую предложили МЫ последним сообщением (кнопка «Согласен с N» на карточке);
-- `unread` — наши и системные сообщения после того, как площадка последний раз открыла переписку.
CREATE OR REPLACE VIEW pub.recon_v1 WITH (security_barrier) AS
SELECT r.id AS request_id, r.publisher_id, pb.domain AS site, r.period, r.asked_at, r.due_at,
       r.verdict, r.decided_at,
       rc.our_volume, rc.their_volume, rc.agreed_volume, COALESCE(rc.cpm, pb.cpm_contract)::numeric AS cpm,
       COALESCE(lm.side, 'система') AS last_side,
       CASE WHEN lm.side = 'мы' THEN lm.volume END AS offer,
       (SELECT count(*) FROM publisher_request_message m
         WHERE m.request_id = r.id AND m.side <> 'площадка'
           AND m.created_at > COALESCE(r.pub_seen_at, '-infinity'::timestamp)) AS unread,
       (SELECT count(*) FROM publisher_request_message m WHERE m.request_id = r.id AND m.side <> 'система') AS messages
  FROM publisher_request r
  JOIN sales_publishers pb ON pb.id = r.publisher_id
  LEFT JOIN publisher_recon rc ON rc.request_id = r.id
  LEFT JOIN LATERAL (SELECT m.side, m.volume FROM publisher_request_message m
                      WHERE m.request_id = r.id AND m.side <> 'система' ORDER BY m.id DESC LIMIT 1) lm ON true
 WHERE r.kind = 'сверка' AND r.publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.recon_v1 TO cabinet;

-- Автор с нашей стороны площадке показывается как «SIMB-AD»: имена сотрудников наружу не отдаём.
-- Цифра — `shows`, не `volume`: имя `volume` в контракте кабинета запрещено прибором (tests/test_cabinet_contract).
CREATE OR REPLACE VIEW pub.recon_message_v1 WITH (security_barrier) AS
SELECT m.id AS message_id, m.request_id, m.side,
       CASE WHEN m.side = 'площадка' THEN m.author_name ELSE 'SIMB-AD' END AS author_name,
       m.body, m.volume AS shows, m.created_at
  FROM publisher_request_message m
  JOIN publisher_request r ON r.id = m.request_id
 WHERE r.kind = 'сверка' AND r.publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.recon_message_v1 TO cabinet;

CREATE OR REPLACE VIEW pub.recon_file_v1 WITH (security_barrier) AS
SELECT f.id AS file_id, f.message_id, m.request_id, f.original_name AS name, f.size_bytes
  FROM publisher_request_file f
  JOIN publisher_request_message m ON m.id = f.message_id
  JOIN publisher_request r ON r.id = m.request_id
 WHERE r.kind = 'сверка' AND r.publisher_id = ANY (pub.allowed_publisher_ids());
GRANT SELECT ON pub.recon_file_v1 TO cabinet;

-- ── 5. право и бэкфилл ─────────────────────────────────────────────────────────────────────────
-- Новая секция по умолчанию закрыта всем; владелец 12.10: «пока только менеджер паблишеров».
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM role_permissions WHERE section = 'dir_publishers_interaction') THEN
        INSERT INTO role_permissions (role_id, section, can_view, can_create, can_edit, can_delete,
                                      can_view_operations, can_approve, deals_scope)
        SELECT r.id, 'dir_publishers_interaction', 1, 0, 1, 0, 0, 0, 'all'
          FROM roles r WHERE r.staff_group = 'publishers';
    END IF;
END $$;
