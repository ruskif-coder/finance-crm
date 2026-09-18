# -*- coding: utf-8 -*-
"""«В размещении» пишет ЗАПУСК площадки, и только он.

18.09.2026 карточка сделки показывала «в размещении» по площадке, у которой РК не
собрана, сама площадка ждёт запуска, а срок ещё не наступил. Поле не врало — его
поставили кнопкой руками. Врала конструкция: один и тот же факт («идёт ли размещение»)
имели право утверждать два места, и разошлись они молча, обеими правдоподобными
надписями сразу.

Прибор держит границу с двух сторон: руками поставить нельзя, запуском — ставится.
"""
import pytest
from sqlalchemy import text

from app import models as _core  # noqa: F401 — регистрирует users для FK
from app.sales import models as _sales  # noqa: F401
from app.launch_prep import models as _lp  # noqa: F401
from app.ad import build, models as _ad  # noqa: F401


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def _fixture(db):
    """Сделка + РК + площадка в ней + пара в сборе запуска. Номера тестовые."""
    from app.ad.models import AdCampaign, AdCampaignPlacement
    from app.launch_prep.models import LaunchPrepTarget

    deal_id = db.execute(text("SELECT id FROM sales_deals ORDER BY id LIMIT 1")).scalar()
    service_id = db.execute(text("SELECT id FROM sales_services ORDER BY id LIMIT 1")).scalar()
    pub_id = db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 1")).scalar()
    if not (deal_id and pub_id and service_id):
        pytest.skip("на стенде нет сделки, площадки или услуги")
    camp = AdCampaign(deal_id=deal_id, status="ожидает сборки")
    db.add(camp)
    db.flush()
    pl = AdCampaignPlacement(campaign_id=camp.id, publisher_id=pub_id, status="ждёт запуска")
    t = LaunchPrepTarget(deal_id=deal_id, publisher_id=pub_id, service_id=service_id,
                         surface_kind="WEB", state="ерид получен")
    db.add_all([pl, t])
    db.commit()
    return camp, pl, t


def _drop(db, camp, t):
    db.execute(text("DELETE FROM launch_prep_target WHERE id = :i"), {"i": t.id})
    db.execute(text("DELETE FROM ad_campaign_placement WHERE campaign_id = :c"), {"c": camp.id})
    db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": camp.id})
    db.commit()


def test_launch_moves_the_pair_into_placement():
    """Запуск площадки переводит её пару — связь по (сделка, площадка)."""
    db = _db()
    camp = t = None
    try:
        camp, pl, t = _fixture(db)
        assert build.mark_target_placed(db, pl, commit=True) == 1
        db.refresh(t)
        assert t.state == "в размещении"
    finally:
        if camp:
            _drop(db, camp, t)
        db.close()


def test_a_pair_that_moved_on_is_not_dragged_back():
    """Назад состояние не ходит: завершённую пару запуск соседней площадки не воскрешает."""
    db = _db()
    camp = t = None
    try:
        camp, pl, t = _fixture(db)
        t.state = "завершён"
        db.commit()
        assert build.mark_target_placed(db, pl, commit=True) == 0
        db.refresh(t)
        assert t.state == "завершён"
    finally:
        if camp:
            _drop(db, camp, t)
        db.close()


def test_the_hand_written_route_refuses_that_state():
    """Ручка перевода отказывает словами, а не молча игнорирует: человек должен узнать,
    ГДЕ это состояние ставится, иначе он просто нажмёт ещё раз."""
    import inspect

    from app.routers import launch_prep as lp
    src = inspect.getsource(lp.move_target)
    assert 'payload.state == "в размещении"' in src
    assert "дашборде трафика" in src
