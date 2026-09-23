# -*- coding: utf-8 -*-
"""Прибор: повторный прогон конвейера годового плана ничего не ломает (аудит 23.09, 3.M3–3.M4).

  · докстрока обещала «неизменившиеся ячейки пропускаются», а код КАЖДУЮ существующую
    сделку писал заново и удалял её медиаплан, создавая новый с новым id: ссылки
    `/accounts/mp/{id}` в разосланных уведомлениях переставали открываться, а предпросмотр
    всегда показывал `unchanged: 0`;
  · план сделки на «МП Отправлено» (отдан клиенту) не был заморожен — повтор стирал то,
    что клиент уже видел.

Всё — в транзакции с откатом, на строке годового плана стенда.
"""
import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import year_plan as yp
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesMediaPlan, SalesYearPlanLine


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def run(db, monkeypatch):
    """Строка плана, по которой конвейер реально создаёт сделки, и способ его запустить."""
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
    for line in db.query(SalesYearPlanLine).order_by(SalesYearPlanLine.id).all():
        if line.brand_id and yp._planned_months(line) and not yp._brief_missing(line):
            body = yp.ConveyorIn(year=line.year, rep_id=line.sales_rep_id, line_id=line.id)
            go = lambda: yp.create_deals(body, db=db, current_user=admin)  # noqa: E731
            if go()["created"] or db.query(SalesDeal).filter(
                    SalesDeal.year_plan_line_id == line.id).count():
                return line, body, admin, go
    pytest.skip("на стенде нет строки плана, по которой конвейер создаёт сделки")


def _plans(db, line):
    deals = [d.id for d in db.query(SalesDeal.id).filter(SalesDeal.year_plan_line_id == line.id)]
    return sorted(p.id for p in db.query(SalesMediaPlan.id).filter(SalesMediaPlan.deal_id.in_(deals)))


def test_second_run_without_changes_touches_nothing(db, run):
    line, body, admin, go = run
    before = _plans(db, line)
    res = go()
    assert res["created"] == 0 and res["updated"] == 0 and res["unchanged"] > 0, res
    assert _plans(db, line) == before, "медиапланы пересозданы — ссылки на них умерли"


def test_preview_says_unchanged(db, run):
    line, body, admin, go = run
    pv = yp.create_deals_preview(body, db=db, current_user=admin)
    assert pv["changed"] == [] and pv["unchanged"] > 0, pv


# Правило владельца 23.09.2026: сделка ДО «Сборки» (МП Подготовка, МП Отправлено, Бронь)
# обновляется из годового плана при каждом прогоне, если на месяце нет замочка; со «Сборки»
# медиаплан зафиксирован, и конвейер сделку не трогает. Днём 23.09 я ошибочно заморозил
# сделку уже на «МП Отправлено» — это правило противоречило владельцу и откачено.

def _stage_by_key(db, key):
    from app.sales.models import SalesStage
    st = db.query(SalesStage).filter(SalesStage.stage_key == key).first()
    if st is None:
        pytest.skip(f"в каталоге нет стадии {key}")
    return st


def test_deal_before_assembly_follows_the_plan(db, run):
    line, body, admin, go = run
    cat = Catalog(db)
    deal = db.query(SalesDeal).filter(SalesDeal.year_plan_line_id == line.id).first()
    deal.our_stage_id = cat.next_of(cat.first().id).id          # «МП Отправлено»
    deal.amount = mark = (deal.amount or 0) + 1                  # разошлась с ячейкой
    db.flush()
    res = go()
    assert not any(x["deal_id"] == deal.id for x in res["in_work"]), res
    db.refresh(deal)
    assert deal.amount != mark, "сделку до «Сборки» конвейер обязан вернуть к плану"


def test_deal_in_assembly_is_frozen(db, run):
    line, body, admin, go = run
    deal = db.query(SalesDeal).filter(SalesDeal.year_plan_line_id == line.id).first()
    deal.our_stage_id = _stage_by_key(db, "launch_prep").id     # «Готовятся к старту»
    # Сделка разошлась с ячейкой: без заморозки конвейер переписал бы её сумму и план.
    deal.amount = mark = (deal.amount or 0) + 1
    db.flush()
    before = _plans(db, line)
    res = go()
    assert any(x["deal_id"] == deal.id for x in res["in_work"]), res
    db.refresh(deal)
    assert deal.amount == mark, "замороженную сделку конвейер переписал"
    assert _plans(db, line) == before


# ── Блокировка двойного запуска — по году, а не по сейлзу (ревью 23.09.2026) ─────────

def test_conveyor_waits_for_a_run_of_the_same_year_under_another_rep(db):
    """Продавец и ведущий аккаунт — два владельца одной строки — запускают конвейер под
    своими сейлзами. Ключ «год × сейлз» не встречался, и общая строка давала две сделки.
    Здесь вторая сессия держит блокировку года; запуск под ДРУГИМ сейлзом обязан ждать."""
    from sqlalchemy import exc, text

    from app.database import engine
    admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
    if admin is None:
        pytest.skip("нужна учётка админа")
    year = 2099
    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:a, :b)"),
                      {"a": yp.CONVEYOR_LOCK, "b": yp.conveyor_lock_key(year)})
        try:
            db.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(exc.OperationalError, match="lock timeout"):
                yp.create_deals(yp.ConveyorIn(year=year, rep_id=987654), db=db,
                                current_user=admin)
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:a, :b)"),
                          {"a": yp.CONVEYOR_LOCK, "b": yp.conveyor_lock_key(year)})


def test_year_out_of_range_is_refused_before_the_lock():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        yp.conveyor_lock_key(99_999)
    assert e.value.status_code == 400
