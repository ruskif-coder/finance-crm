"""Ответственный сейлз у рекламодателя: назначение и его сохранность.

Прибор ставится на два места, где поле молча теряется, а увидеть это можно только
в следующем медиаплане — уже не поняв, кто виноват:

  · назначение принимает УЧЁТКУ и заводит профиль (`ensure_rep`). Возьми ручка id
    строки `sales_reps` — выбирать было бы некого: справочник заполнен не всеми
    (20 учёток против 11 профилей, замер 03.09.2026);
  · `update_advertiser` переписывает свои поля ЦЕЛИКОМ. Попади сейлз в тело этой
    формы — правка сайта обнуляла бы назначение. Поэтому он отдельной ручкой, и
    тест сторожит именно это: правка карточки назначение не трогает.

Эндпоинты зовутся напрямую с фиктивным admin — как в test_launch_prep_directories.py.
"""
from types import SimpleNamespace

import pytest

import app.notify.models  # noqa: F401  — иначе маппер не найдёт notification_profiles
from app.database import SessionLocal
from app.models import Role, User
from app.routers.sales_directories import (AdvertiserIn, AdvertiserRepIn,
                                           list_advertisers,
                                           set_advertiser_sales_rep, update_advertiser)
from app.sales.models import SalesAdvertiser, SalesRep

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None,
                              email='test', name='тест')


ADV_NAME = 'ТЕСТ рекламодатель rep'
# После правки карточки каноничным именем становится короткое — чистим оба.
ADV_SHORT = 'ТЕСТ rep'
SELLER_MAIL = 'test-adv-rep@example.invalid'


def _purge(session):
    """Ручки коммитят, поэтому rollback за собой не убирает: чистим явно и по порядку
    (рекламодатель ссылается на профиль, профиль — на учётку). Журнал действий тоже
    артефакт: строки о назначении переживают удаление рекламодателя."""
    from app.models import AuditLog
    adv_ids = [i for (i,) in session.query(SalesAdvertiser.id)
               .filter(SalesAdvertiser.name.in_((ADV_NAME, ADV_SHORT))).all()]
    if adv_ids:
        (session.query(AuditLog)
         .filter(AuditLog.action == 'set_advertiser_sales_rep',
                 AuditLog.entity_id.in_(adv_ids)).delete(synchronize_session=False))
        (session.query(SalesAdvertiser)
         .filter(SalesAdvertiser.id.in_(adv_ids)).delete(synchronize_session=False))
    uid = session.query(User.id).filter(User.email == SELLER_MAIL).first()
    if uid:
        session.query(SalesRep).filter(SalesRep.user_id == uid[0]).delete(synchronize_session=False)
        session.query(User).filter(User.id == uid[0]).delete(synchronize_session=False)
    session.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


@pytest.fixture
def seller(db):
    """Учётка с рабочей группой роли «Продавец» и БЕЗ профиля ответственного."""
    role = db.query(Role).filter(Role.staff_group == 'seller').first()
    if role is None:
        pytest.skip('в базе нет роли с рабочей группой seller')
    u = User(name='Тест Сейлз', email=SELLER_MAIL,
             hashed_password='x', role_id=role.id, is_active=1)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def adv(db):
    a = SalesAdvertiser(name=ADV_NAME, short_name=ADV_SHORT, is_active=True)
    db.add(a)
    db.commit()
    return a


def test_assignment_takes_a_user_and_creates_the_profile(db, adv, seller):
    """Принимаем учётку — профиль под ней заводится сам."""
    assert db.query(SalesRep).filter(SalesRep.user_id == seller.id).first() is None
    out = set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=seller.id), db, _FAKE_ADMIN)
    rep = db.query(SalesRep).filter(SalesRep.user_id == seller.id).first()
    assert rep is not None, 'профиль ответственного не заведён'
    assert out['sales_rep_id'] == rep.id
    assert db.query(SalesAdvertiser).get(adv.id).sales_rep_id == rep.id


def test_editing_the_card_does_not_clear_the_rep(db, adv, seller):
    """Правка названия/сайта не должна снимать назначение."""
    set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=seller.id), db, _FAKE_ADMIN)
    rep_id = db.query(SalesAdvertiser).get(adv.id).sales_rep_id
    update_advertiser(adv.id, AdvertiserIn(short_name=ADV_SHORT, website='https://example.invalid'),
                      db, _FAKE_ADMIN)
    assert db.query(SalesAdvertiser).get(adv.id).sales_rep_id == rep_id


def test_unassign_clears_it(db, adv, seller):
    set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=seller.id), db, _FAKE_ADMIN)
    set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=None), db, _FAKE_ADMIN)
    assert db.query(SalesAdvertiser).get(adv.id).sales_rep_id is None


def test_listing_gives_both_ids(db, adv, seller):
    """Списку нужны оба: хранится профиль, выбирают учётку."""
    set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=seller.id), db, _FAKE_ADMIN)
    row = next(x for x in list_advertisers(True, db, _FAKE_ADMIN)['items'] if x['id'] == adv.id)
    assert row['sales_rep_user_id'] == seller.id
    assert row['sales_rep'] == 'Тест Сейлз'
    assert row['sales_rep_id'] == db.query(SalesAdvertiser).get(adv.id).sales_rep_id


def test_disabled_account_is_refused(db, adv, seller):
    from fastapi import HTTPException
    seller.is_active = 0
    db.flush()
    with pytest.raises(HTTPException) as e:
        set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=seller.id), db, _FAKE_ADMIN)
    assert e.value.status_code == 400


def test_year_plan_catalog_carries_the_advertisers_rep(db, adv, seller):
    """Годовой план подставляет сейлза в бриф строки из своего каталога.

    Прибор поставлен по итогам прогона 21.09.2026: у этой половины работы его не было
    вовсе, и пропажа поля в `_catalog` проявилась бы не ошибкой, а тихо — «почему-то
    перестало подставляться», через неделю и не на том экране.
    """
    from app.routers.year_plan import _catalog
    set_advertiser_sales_rep(adv.id, AdvertiserRepIn(user_id=seller.id), db, _FAKE_ADMIN)
    row = next(a for a in _catalog(db)['advertisers'] if a['id'] == adv.id)
    assert row['sales_rep_user_id'] == seller.id, (
        'каталог годового плана перестал отдавать сейлза рекламодателя — '
        'подстановка в бриф строки замолчит')
