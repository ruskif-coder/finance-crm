# -*- coding: utf-8 -*-
"""Поверхность площадки в сделке, пока ей ничего не отправляли, — меняется добавлением с другой поверхностью (владелец 18.11.2026).

Повод: четыре копии сделок еФарм WEB (8JWW6M, LQADED, G3FTLM, 9QLCCS) перевели в медиаплане на APP, а скопированные получатели
остались web; «+ Площадки» с app отказывал «уже добавлена с поверхностью web — заведите вторую сделку», и снимать получателей
пришлось на проде руками.

Поломки, которые ловит набор:
- неотправленная площадка снова получает отказ вместо смены поверхности;
- поверхность меняется у площадки, которой уже отправляли комплект (пара есть) — запрос по вебу молча стал бы запросом по приложению;
- поверхность меняется у площадки, адресованной ДРУГОМУ креативу — его материал сделан под прежнюю поверхность."""
import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepCreativeSet, LaunchPrepPair, LaunchPrepSetTarget, LaunchPrepTarget
from app.routers.launch_prep import _attach
from app.sales.models import SalesDeal, SalesPublisher, SalesService


@pytest.fixture
def ctx():
    db = SessionLocal()
    try:
        used = {p for (p,) in db.query(LaunchPrepTarget.publisher_id).distinct()}
        deal = db.query(SalesDeal).order_by(SalesDeal.id).first()
        pub = db.query(SalesPublisher).filter(~SalesPublisher.id.in_(used or {0})).order_by(SalesPublisher.id).first() \
            or db.query(SalesPublisher).order_by(SalesPublisher.id).first()
        svc = db.query(SalesService).order_by(SalesService.id).first()
        db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == deal.id,
                                          LaunchPrepTarget.publisher_id == pub.id).delete(synchronize_session=False)
        db.flush()
        yield db, deal, pub, svc
    finally:
        db.rollback()
        db.close()


def _target(db, deal, pub):
    return db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == deal.id, LaunchPrepTarget.publisher_id == pub.id).one()


def _set(db, deal, no):
    s = LaunchPrepCreativeSet(deal_id=deal.id, no=no)
    db.add(s)
    db.flush()
    return s


def test_unsent_target_switches_surface(ctx):
    db, deal, pub, svc = ctx
    _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "web"}], None)
    _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "app"}], None)
    db.flush()
    assert _target(db, deal, pub).surface_kind == "app"


def test_unsent_target_in_this_set_switches_and_stays_addressed(ctx):
    db, deal, pub, svc = ctx
    s = _set(db, deal, 9701)
    _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "web"}], s.id)
    db.flush()      # в жизни — отдельный запрос с коммитом; у сессий проекта autoflush=False
    _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "app"}], s.id)
    db.flush()
    t = _target(db, deal, pub)
    assert t.surface_kind == "app"
    assert db.query(LaunchPrepSetTarget).filter(LaunchPrepSetTarget.target_id == t.id).count() == 1


def test_sent_target_keeps_surface_and_refuses(ctx):
    db, deal, pub, svc = ctx
    s = _set(db, deal, 9702)
    _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "web"}], s.id)
    t = _target(db, deal, pub)
    db.add(LaunchPrepPair(set_id=s.id, target_id=t.id))
    db.flush()
    with pytest.raises(HTTPException) as e:
        _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "app"}], None)
    assert e.value.status_code == 400 and "отправляли" in e.value.detail
    assert _target(db, deal, pub).surface_kind == "web"


def test_target_of_another_creative_keeps_surface_and_refuses(ctx):
    db, deal, pub, svc = ctx
    other, mine = _set(db, deal, 9703), _set(db, deal, 9704)
    _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "web"}], other.id)
    db.flush()
    with pytest.raises(HTTPException) as e:
        _attach(db, deal, svc, [{"publisher_id": pub.id, "surface_kind": "app"}], mine.id)
    assert e.value.status_code == 400
    assert _target(db, deal, pub).surface_kind == "web"
