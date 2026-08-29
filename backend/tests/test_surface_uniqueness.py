"""Поверхность площадки в сделке — одна. Прибор на условие, а не на код.

Поверхность (web / app) решается ВЫШЕ, на услуге: площадка получает запрос по
приложению, только если оно у неё подключено (владелец 28.08.2026). Поэтому «частичное
решение по поверхностям» из эталона хендоффа нам не нужно — задачи, которую оно решает,
у нас не возникает.

Держится это не на коде, а на СОСТОЯНИИ СПРАВОЧНИКА: пока ни у одной площадки одна
услуга не подключена и на web, и на app, получатель однозначен. Замер 28.08.2026 — ноль
таких связок.

В день, когда связка появится, модель потребует решения: `launch_prep_target` уникален
по паре «сделка × площадка», и поверхность там одна. Тест ловит этот день. Он не
запрещает связку — он не даёт ей появиться незаметно.
"""
from sqlalchemy import text

from app.database import SessionLocal


def test_service_is_not_connected_to_both_surfaces():
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT p.name, s.name AS service,
                   string_agg(ps.surface_kind, '+' ORDER BY ps.surface_kind) AS surfaces
            FROM sales_publisher_services ps
            JOIN sales_publishers p ON p.id = ps.publisher_id
            JOIN sales_services   s ON s.id = ps.service_id
            WHERE ps.is_active
            GROUP BY p.name, s.name
            HAVING count(DISTINCT ps.surface_kind) > 1
        """)).all()
    finally:
        db.close()

    assert not rows, (
        "В справочнике появилась площадка с одной услугой на ДВУХ поверхностях: "
        + "; ".join(f"{r.name} · {r.service} ({r.surfaces})" for r in rows)
        + ". Получатель сделки уникален по паре «сделка × площадка», и поверхность у "
          "него одна — решите, как описывать такое размещение, прежде чем отправлять "
          "по нему креативы.")
