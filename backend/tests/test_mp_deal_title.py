"""Имя медиаплана — источник имени сделки (владелец 03.09.2026).

Поймано на живой сделке ZCBPLS: аккаунт переименовал план, а сделка осталась с прежним
именем, и это выглядело как «переименование не сработало». Поля жили независимо, и
единственным способом свести их был ручной клик «собрать название» в реестре.

Прибор держит ровно правило, а не реализацию: после сохранения плана имя сделки равно
имени плана. И вторую половину правила — при ДВУХ группах планов сделка не
переименовывается: названий-кандидатов столько же, сколько групп.
"""
from types import SimpleNamespace

import pytest

import app.ord.models  # noqa: F401  — мапперы настраиваются на первом flush, и без
# этого импорта SalesDeal.ord_initial_contract_id не находит свою таблицу (готча ORM).
from app.database import SessionLocal
from app.routers import media_plans as mp
from app.sales.models import SalesDeal, SalesMediaPlan

PREFIX = 'MPTITLEtest'


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    # Убираем за собой И до, и после: упавший прогон иначе оставит мусор, на котором
    # следующий прогон посчитает не то.
    from app.models import AuditLog
    for d in s.query(SalesDeal).filter(SalesDeal.bitrix_id.like(f'{PREFIX}%')).all():
        # Журнал действий чистим тоже: перенос из плана пишет строку `deal_from_mp`, и без
        # этого каждый прогон оставлял бы в «Журнале действий» запись о несуществующей
        # сделке. Прогон 08.09.2026 нашёл здесь 8 таких сирот.
        s.query(AuditLog).filter(AuditLog.entity_type == 'sales_deal',
                                 AuditLog.entity_id == d.id).delete(synchronize_session=False)
        s.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == d.id).delete(
            synchronize_session=False)
        s.delete(d)
    s.commit()
    s.close()


def _deal(db, title='старое имя'):
    d = SalesDeal(bitrix_id=f'{PREFIX}-{title}', title=title)
    db.add(d)
    db.flush()
    return d


def _plan(db, deal, title, group_id=None):
    p = SalesMediaPlan(group_id=group_id, version=1, title=title, deal_id=deal.id)
    db.add(p)
    db.flush()
    if p.group_id is None:
        p.group_id = p.id
        db.flush()
    return p


_USER = SimpleNamespace(id=None, name='тест',
                        role=SimpleNamespace(key='admin', is_master=True))


def test_plan_title_becomes_the_deal_title(db):
    """Одна группа планов — имя плана переезжает на сделку."""
    deal = _deal(db)
    plan = _plan(db, deal, 'Dr. Reddy’s | Хелинорм | G4M | еФарм WEB | 2026-09')
    db.commit()

    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.title == plan.title, (
        'имя сделки не пошло за именем плана — ровно то, что владелец видел на ZCBPLS'
    )


def test_second_plan_group_stops_the_rename(db):
    """Две группы планов — сделку не переименовываем.

    Кандидатов на имя столько же, сколько групп, и взять последний сохранённый значило
    бы переименовывать сделку тем планом, который тронули позже.
    """
    deal = _deal(db, 'имя сделки')
    first = _plan(db, deal, 'план один')
    _plan(db, deal, 'план два')
    db.commit()

    mp._sync_deal_from_plan(db, first, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.title == 'имя сделки', 'сделку переименовали при двух группах планов'


def test_sync_is_idempotent_and_ignores_empty_title(db):
    """Повторный вызов ничего не меняет, пустое имя плана сделку не затирает."""
    deal = _deal(db, 'имя сделки')
    plan = _plan(db, deal, '   ')
    db.commit()

    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.title == 'имя сделки', 'пустое имя плана затёрло имя сделки'

    plan.title = 'новое имя'
    db.commit()
    mp._sync_deal_from_plan(db, plan, _USER)
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.title == 'новое имя'
