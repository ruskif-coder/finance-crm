-- «Ваша команда» в кабинете площадки берётся из НАСТРОЙКИ, а не из сделки.
--
-- Было: `pub.team_v1` собирал людей из сделок, которые касаются площадки —
-- `account_manager_id` и `traffic_manager_id`. Захардкожено там ничего не было, но
-- состав получался побочным следствием того, кто ведёт кампанию: сменился аккаунт
-- сделки — у площадки в кабинете молча сменился контакт, и наоборот, пока кампании нет,
-- команда пуста, хотя обращаться к нам есть с чем.
--
-- Стало: список задаётся явно — `cabinet_our_contact`, общий на все кабинеты (решение
-- владельца 30.08.2026, экран «Кабинеты паблишеров» → «Наши контакты у площадок»).
--
-- **Аккаунт и трафик СДЕЛКИ сюда не входят намеренно.** Владелец 30.08.2026: «будем ли
-- мы показывать аккаунта сделки и траффика сделки — мы ещё не решили». Значение по
-- умолчанию выбрано «не показываем»: лишний контакт наружу убрать труднее, чем добавить.
-- Вернуть их — это UNION к этому представлению, миграция схемы не нужна.
--
-- `sort_order` добавлен в КОНЕЦ списка колонок: `CREATE OR REPLACE VIEW` разрешает
-- дописывать колонки, но не переименовывать и не убирать существующие. Порядок — часть
-- смысла: первым площадка видит того, к кому идти сначала.
--
-- Область видимости не применяется: контакты общие, а не «этой площадки». Строка
-- размножается по `pub.allowed_publisher_ids()`, чтобы форма ответа осталась прежней —
-- потребитель группирует по `publisher_id`.

CREATE OR REPLACE VIEW pub.team_v1 WITH (security_barrier) AS
    SELECT pid AS publisher_id,
           r.id AS rep_id,
           r.name,
           oc.role,
           u.email,
           oc.sort_order
      FROM cabinet_our_contact oc
      JOIN sales_reps r ON r.id = oc.rep_id
      LEFT JOIN users u ON u.id = r.user_id
      CROSS JOIN LATERAL unnest(pub.allowed_publisher_ids()) AS pid
     WHERE oc.is_shown;

GRANT SELECT ON pub.team_v1 TO cabinet;

-- Доп. каналы связи площадки — в её же профиль.
--
-- `messenger_note` заполняется в карточке паблишера («доп. каналы связи») и до сих пор
-- наружу не отдавалось: площадка не видела то, о чём мы с ней сами договорились.
-- Колонка дописывается В КОНЕЦ — `CREATE OR REPLACE VIEW` не даёт менять существующие.
CREATE OR REPLACE VIEW pub.profile_v1 WITH (security_barrier) AS
    SELECT id AS publisher_id,
           name,
           domain,
           kind,
           network,
           chat_title,
           chat_url,
           chat_url_max,
           media_kit_filename,
           tech_requirements,
           messenger_note
      FROM sales_publishers p
     WHERE id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.profile_v1 TO cabinet;
