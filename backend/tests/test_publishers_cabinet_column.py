# -*- coding: utf-8 -*-
"""Колонка «Кабинет» в реестре площадок: цвет берётся из состояния кабинета.

Прибор стоит по двум причинам, и обе уже случались в этом проекте.

Первая — **колонка с читателем и без писателя**. Экран рисует кружок по полю `cabinet`
из ответа ручки. Пропадёт поле (перепишут выборку, переименуют связь) — колонка станет
сплошным прочерком: это НЕ похоже на поломку, это похоже на «кабинетов ещё не завели».

Вторая — **состояние кабинета читается в двух местах**. Реестр показывает его цветом,
кабинет им же запирает вход. Разойдись они — площадка светилась бы зелёным при закрытом
доступе, и вопрос «почему он не может войти» стал бы неотвечаемым.

Эндпоинт вызывается напрямую с фиктивным admin-пользователем, как в
test_launch_prep_directories.py.
"""
from types import SimpleNamespace

import pytest

from app.cabinet.models import Cabinet, CabinetPublisher, CABINET_STATES
from app.database import SessionLocal
from app.routers.publishers import list_publishers
from app.sales.models import SalesPublisher

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None,
                              email='test', name='тест')


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _free_publisher(db):
    """Площадка, не привязанная ни к одному кабинету."""
    taken = {pid for (pid,) in db.query(CabinetPublisher.publisher_id).all()}
    return (db.query(SalesPublisher)
            .filter(SalesPublisher.id.notin_(taken) if taken else True)
            .order_by(SalesPublisher.id).first())


@pytest.fixture
def stand(db):
    """Площадка вне кабинетов + свой кабинет на неё. Состояние меняет сам тест."""
    free = _free_publisher(db)
    if free is None:
        pytest.skip('нужна площадка вне кабинетов')
    cab = Cabinet(name='ТЕСТ кабинет колонки', kind='площадка', state='черновик')
    db.add(cab)
    db.flush()
    db.add(CabinetPublisher(publisher_id=free.id, cabinet_id=cab.id))
    db.flush()
    return free, cab


def _row(db, pid):
    # `service_id` передаём явно: у эндпоинта это `Query(None)`, и при прямом вызове —
    # в обход FastAPI — в функцию приезжает сам объект Query, а он истинный. Фильтр
    # тогда пытается сравнить id со служебным объектом и падает на ровном месте.
    items = list_publishers(service_id=None, db=db, current_user=_FAKE_ADMIN)["items"]
    return next(r for r in items if r["id"] == pid)


def test_unbound_publisher_has_no_cabinet(db):
    """Прочерк на экране — это ОТСУТСТВИЕ ключа, а не забытое поле."""
    free = _free_publisher(db)
    if free is None:
        pytest.skip('нужна площадка вне кабинетов')
    assert _row(db, free.id)["cabinet"] is None


def test_bound_publisher_carries_name_and_state(db, stand):
    """Имя нужно подсказке, состояние — цвету. Без имени кружок молчит о том, чей он."""
    pub, cab = stand
    got = _row(db, pub.id)["cabinet"]
    assert got == {"id": cab.id, "name": cab.name, "state": "черновик"}


@pytest.mark.parametrize("state", CABINET_STATES)
def test_every_state_reaches_the_screen(db, stand, state):
    """Каждое состояние доезжает до экрана как есть, без схлопывания.

    Цветовую карту сам прибор проверить не может — она в JS, а фронт живёт в другом
    контейнере. Но карта построена по `CABINET_STATES`, и неизвестное ей состояние
    рисуется серым «черновиком», то есть новое состояние появится на экране молча.
    Поэтому тест ходит по КАЖДОМУ значению перечисления: добавят четвёртое — здесь
    станет видно, что про цвет для него никто не подумал."""
    pub, cab = stand
    cab.state = state
    db.flush()
    assert _row(db, pub.id)["cabinet"]["state"] == state
