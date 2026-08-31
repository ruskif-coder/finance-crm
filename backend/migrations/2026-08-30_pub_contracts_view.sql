-- Юрлица площадки и её договоры — в кабинет.
--
-- Площадка видит, от какого юрлица она с нами работает и какие договоры к нему
-- привязаны. До сих пор наружу не отдавалось ничего из этого: реквизиты своей же
-- стороны площадка могла проверить только письмом.
--
-- ДВА представления, а не одно с LEFT JOIN. Договор привязан к ПЛОЩАДКЕ
-- (`sales_publisher_contracts`), а к юрлицу — только через карточку договора
-- (`contracts.counterparty_id`), которой у 26 из 47 записей нет: они заведены голым
-- номером. Склеив их в одно представление, пришлось бы либо потерять такие договоры,
-- либо приписать их произвольному юрлицу. Здесь оба факта отдаются как есть, а
-- раскладку по карточкам делает кабинет — и делает её видимой: договор без юрлица
-- попадает в отдельную группу, а не растворяется.

CREATE OR REPLACE VIEW pub.counterparty_v1 AS
    SELECT pc.publisher_id,
           cp.id AS counterparty_id,
           cp.name,
           cp.inn,
           -- Ставка, которую площадка выставляет НАМ: с её стороны это её НДС, с нашей —
           -- расход. Поле одно, читается по-разному, поэтому названо нейтрально.
           cp.vat_rate_expense AS vat_rate
      FROM sales_publisher_counterparties pc
      JOIN counterparties cp ON cp.id = pc.counterparty_id
     WHERE pc.publisher_id = ANY (pub.allowed_publisher_ids());

CREATE OR REPLACE VIEW pub.contract_v1 AS
    SELECT spc.publisher_id,
           c.counterparty_id,
           -- Номер из карточки, а при её отсутствии — тот, которым договор завели.
           -- Пустого номера не бывает: он и есть имя договора.
           coalesce(c.contract_number, spc.number_raw) AS number,
           c.contract_date AS signed_at,
           c.end_date_text AS valid_until,
           spc.role,
           spc.is_archived,
           -- Ссылка НЕ отдаётся: файл лежит в нашем хранилище, и раздача его наружу —
           -- отдельное решение с проверкой прав, а не побочный эффект витрины.
           (spc.document_path IS NOT NULL OR spc.document_url IS NOT NULL) AS has_file
      FROM sales_publisher_contracts spc
      LEFT JOIN contracts c ON c.id = spc.contract_id
     WHERE spc.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.counterparty_v1 TO cabinet;
GRANT SELECT ON pub.contract_v1 TO cabinet;
