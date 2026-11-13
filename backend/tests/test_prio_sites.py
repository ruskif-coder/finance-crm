# -*- coding: utf-8 -*-
"""Площадки в системе приоритезации — вкладка «Приоритезация» админ панели трафика (владелец 13.11.2026: «в админке трафика будет
раздел приоритезация с подключением площадок и их id»).

Поломки: номер нельзя ни поставить, ни снять (запрос и запуск заперты «нет site_id»); один номер у двух площадок — статистика и
запуск уйдут не той аптеке; номер-строка или ноль принимаются; правка не видна в журнале."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.prio import sites as PS


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _two(db):
    rows = db.execute(text("""SELECT id FROM sales_publishers WHERE is_active AND coalesce(status, '') <> 'АРХИВ'
                              ORDER BY id LIMIT 2""")).scalars().all()
    if len(rows) < 2:
        pytest.skip("на стенде меньше двух активных площадок")
    db.execute(text("UPDATE sales_publishers SET prio_site_id = NULL WHERE id = ANY(:i)"), {"i": rows})
    db.flush()
    return rows


def test_list_has_every_active_publisher_and_connection_flag(db):
    a, b = _two(db)
    PS.set_site(db, a, 990001)
    rows = {r["id"]: r for r in PS.list_sites(db)}
    assert rows[a]["site_id"] == 990001 and rows[a]["connected"] is True
    assert rows[b]["site_id"] is None and rows[b]["connected"] is False
    assert {"id", "name", "site_id", "connected", "requests"} <= set(rows[a])


def test_number_is_positive_integer_and_unique(db):
    a, b = _two(db)
    PS.set_site(db, a, 990002)
    with pytest.raises(PS.PrioError) as e:
        PS.set_site(db, b, 990002)
    assert e.value.status == 409
    for bad in (0, -5):
        with pytest.raises(PS.PrioError) as e:
            PS.set_site(db, b, bad)
        assert e.value.status == 400


def test_clearing_disconnects(db):
    a, _ = _two(db)
    PS.set_site(db, a, 990003)
    PS.set_site(db, a, None)
    assert db.execute(text("SELECT prio_site_id FROM sales_publishers WHERE id = :i"), {"i": a}).scalar() is None


def test_unknown_publisher_is_404(db):
    with pytest.raises(PS.PrioError) as e:
        PS.set_site(db, 10 ** 9, 1)
    assert e.value.status == 404


def test_too_big_number_is_400_not_a_database_error(db):
    a, _ = _two(db)
    with pytest.raises(PS.PrioError) as e:
        PS.set_site(db, a, 3_000_000_000)
    assert e.value.status == 400


def test_service_flag_follows_publisher_registry(db):
    """Колонка «Услуга в реестре» (владелец 13.11.2026): у площадки включена услуга «Приоритезация» в реестре паблишеров.
    Поломка: флаг берётся не из sales_publisher_services или не гаснет при выключенной услуге."""
    a, _ = _two(db)
    svc = db.execute(text("SELECT id FROM sales_services WHERE name = 'Приоритезация'")).scalar()
    kind = db.execute(text("SELECT kind FROM sales_publisher_surfaces WHERE publisher_id = :p ORDER BY kind LIMIT 1"), {"p": a}).scalar()
    if svc is None or kind is None:
        pytest.skip("на стенде нет услуги «Приоритезация» или поверхности у площадки")
    db.execute(text("DELETE FROM sales_publisher_services WHERE publisher_id = :p AND service_id = :s"), {"p": a, "s": svc})
    db.flush()
    assert {r["id"]: r for r in PS.list_sites(db)}[a]["service"] is False
    db.execute(text("INSERT INTO sales_publisher_services (publisher_id, surface_kind, service_id, is_active) VALUES (:p, :k, :s, true)"),
               {"p": a, "k": kind, "s": svc})
    db.flush()
    assert {r["id"]: r for r in PS.list_sites(db)}[a]["service"] is True
    db.execute(text("UPDATE sales_publisher_services SET is_active = false WHERE publisher_id = :p AND service_id = :s"), {"p": a, "s": svc})
    db.flush()
    assert {r["id"]: r for r in PS.list_sites(db)}[a]["service"] is False
