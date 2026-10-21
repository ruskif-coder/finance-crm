# -*- coding: utf-8 -*-
"""Сделки пакета идут за его статусом (владелец 19.10.2026, п. 2 «делаем»).

Пакет в «ждём оплату» → сделки в «Оплату»; в «архив» → в «Архив успешных сделок». Откат: архив → «ждём оплату» возвращает
сделки в «Оплату», «ждём оплату» → «выставление» — в «Подготовку ДС». Сделку, которую увели со стадии пакета руками, не трогаем.
Живые сделки стенда, транзакция откатывается, уведомления подменены."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import deal_stages as DS
from app.master_deal import status as ST


class _U:
    id = None
    name = "тест"


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    db = SessionLocal()
    m = db.query(MasterDeal).join(MasterDeal.__table__.c.id == MasterDeal.id).first() if False else \
        db.query(MasterDeal).filter(MasterDeal.id.in_(text("SELECT master_deal_id FROM master_deal_items"))).first()
    if m is None:
        pytest.skip("на стенде нет пакета со сделками")
    # исходная точка — сделки пакета на «Подготовке ДС», куда их ставит «Отправить в ДО» (не зависеть от того, где пакет сейчас на стенде)
    db.execute(text("""UPDATE sales_deals SET our_stage_id = (SELECT id FROM sales_stages WHERE name = 'Подготовка ДС')
                        WHERE id IN (SELECT deal_id FROM master_deal_items WHERE master_deal_id = :m)"""), {"m": m.id})
    try:
        yield db, m
    finally:
        db.rollback()
        db.close()


def _stages(db, m):
    return {r[0] for r in db.execute(text("""SELECT st.name FROM master_deal_items i JOIN sales_deals d ON d.id = i.deal_id
                                              JOIN sales_stages st ON st.id = d.our_stage_id WHERE i.master_deal_id = :m"""), {"m": m.id})}


def test_deals_follow_package_forward_and_back(env):
    db, m = env
    m.status = ST.WAIT_PAY
    out = DS.follow(db, m, ST.ISSUE, _U())
    assert _stages(db, m) == {"Оплата"} and out["moved"]
    m.status = ST.ARCHIVE
    DS.follow(db, m, ST.WAIT_PAY, _U())
    assert _stages(db, m) == {"Архив успешных сделок"}
    m.status = ST.WAIT_PAY
    DS.follow(db, m, ST.ARCHIVE, _U())
    assert _stages(db, m) == {"Оплата"}
    m.status = ST.ISSUE
    DS.follow(db, m, ST.WAIT_PAY, _U())
    assert _stages(db, m) == {"Подготовка ДС"}


def test_deal_moved_away_by_hand_is_left_alone(env):
    db, m = env
    did = db.execute(text("SELECT deal_id FROM master_deal_items WHERE master_deal_id = :m LIMIT 1"), {"m": m.id}).scalar()
    other = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    db.execute(text("UPDATE sales_deals SET our_stage_id = :s WHERE id = :d"), {"s": other, "d": did})
    m.status = ST.WAIT_PAY
    out = DS.follow(db, m, ST.ISSUE, _U())
    assert db.execute(text("SELECT our_stage_id FROM sales_deals WHERE id = :d"), {"d": did}).scalar() == other
    assert out["skipped"], "сделку не с той стадии пропустили молча — её надо назвать"


def test_statuses_without_stage_do_not_move(env):
    db, m = env
    before = _stages(db, m)
    m.status = ST.WAIT_1C
    DS.follow(db, m, ST.AGREE, _U())
    assert _stages(db, m) == before
