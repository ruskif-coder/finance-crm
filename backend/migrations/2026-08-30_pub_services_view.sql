-- Услуги, закреплённые за площадкой, — в кабинет.
--
-- Площадка видит, что за ней числится: «еФарм WEB · APP», «Альфарм-Таргет WEB». Те же
-- чипы стоят у нас на экране «Кабинеты паблишеров», и до сих пор наружу они не
-- отдавались — площадка не могла проверить, правильно ли мы её завели.
--
-- Отдельное представление, а не колонка в `pub.profile_v1`: услуг у площадки несколько,
-- и список в одну строку профиля не укладывается. Поверхности НЕ сворачиваются здесь —
-- сворачивает потребитель: витрина отдаёт факты, а «WEB · APP одной строкой» это
-- решение экрана, и второе такое решение в SQL разошлось бы с первым.
--
-- Область — та же, что у всех витрин: `pub.allowed_publisher_ids()`. Служебная учётка
-- увидит услуги всех площадок, обычная — только своих.

CREATE OR REPLACE VIEW pub.publisher_service_v1 WITH (security_barrier) AS
    SELECT ps.publisher_id,
           sv.name AS service,
           ps.surface_kind,
           sv.sort_order
      FROM sales_publisher_services ps
      JOIN sales_services sv ON sv.id = ps.service_id
     WHERE ps.is_active
       AND ps.publisher_id = ANY (pub.allowed_publisher_ids());

GRANT SELECT ON pub.publisher_service_v1 TO cabinet;
