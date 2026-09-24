# -*- coding: utf-8 -*-
"""Сделка рождается из медиаплана — второй путь, наравне с конвейером годового плана.

Годовой план собирает сделки пачкой: строка плана × месяц → сделка + прикреплённый МП.
Малый медиаплан аккаунт собирает руками, и сделка появляется уже из него. Пути два, и
они параллельные: конвейер не отменяет ручной, ручной не отменяет конвейер.

Что здесь держится:

  · сделка встаёт на ПЕРВУЮ стадию — план ещё не проверен, и двигать его дальше должна
    отметка «Проверено», а не факт создания сделки. Иначе гейт снова станет двойным;
  · привязка пишется во ВСЕ версии группы — иначе следующая версия родится без сделки,
    а с ней потеряет и всё своё состояние;
  · ответственные плана — id ПОЛЬЗОВАТЕЛЕЙ, у сделки — id `SalesRep`; забытый перевод
    даёт сделку, назначенную на чужого человека (или ни на кого).
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import AuditLog, User
from app.ord import models as _ord_models   # noqa: F401  (маппер sales_deals → ord_*)
from app.routers import media_plans as mp
from app.sales.catalog import Catalog
from app.sales.models import (SalesAdvertiser, SalesBrand, SalesDeal, SalesMediaPlan,
                              SalesMediaPlanRow, SalesRep)

TITLE = '[тест] сделка из МП'


def _purge(db):
    """Убирает и планы, и рождённые ими сделки. Сделку ищем по заголовку: он собран
    шаблоном и начинается не с нашей метки, поэтому идём от плана к его сделке."""
    db.rollback()
    plans = db.query(SalesMediaPlan).filter(SalesMediaPlan.title.like(f'{TITLE}%')).all()
    dids = {p.deal_id for p in plans if p.deal_id}
    pids = [p.id for p in plans]
    if pids:
        db.query(SalesMediaPlanRow).filter(
            SalesMediaPlanRow.plan_id.in_(pids)).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.entity_type == 'media_plan',
                                  AuditLog.entity_id.in_(pids)).delete(synchronize_session=False)
    for p in plans:
        db.delete(p)
    db.flush()
    if dids:
        db.query(AuditLog).filter(AuditLog.entity_type == 'sales_deal',
                                  AuditLog.entity_id.in_(dids)).delete(synchronize_session=False)
        db.query(SalesDeal).filter(SalesDeal.id.in_(dids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def env():
    db = SessionLocal()
    _purge(db)
    brand = (db.query(SalesBrand).join(SalesAdvertiser, SalesAdvertiser.id == SalesBrand.advertiser_id)
             .filter(SalesBrand.advertiser_id.isnot(None)).first())
    rep = (db.query(SalesRep).join(User, User.id == SalesRep.user_id)
           .filter(User.is_active == 1).first())
    actor = db.query(User).filter(User.is_active == 1).first()
    if not (brand and rep and actor and Catalog(db).first()):
        db.close()
        pytest.skip('нужен бренд с рекламодателем, сейлз с учёткой и каталог стадий')

    def _mk(_rows=True, **kw):
        """План без сделки: ровно то состояние, из которого жмут «Создать сделку»."""
        fields = dict(title=TITLE, version=1, advertiser_id=brand.advertiser_id,
                      brand_id=brand.id, period='2026-10', amount_net=500000,
                      amount_gross=610000, sales_rep_id=rep.user_id, created_by=actor.id)
        fields.update(kw)
        p = SalesMediaPlan(**fields)
        db.add(p)
        db.flush()
        p.group_id = p.id
        if _rows:
            db.add(SalesMediaPlanRow(plan_id=p.id, sort_order=0, position='Спецпроект',
                                     model='CPM', volume=1000000, unit_price=500))
        db.commit()
        return p

    try:
        yield SimpleNamespace(db=db, mk=_mk, brand=brand, rep=rep, actor=actor,
                              first=Catalog(db).first())
    finally:
        _purge(db)
        db.close()


def test_a_deal_from_a_plan_starts_where_the_plan_is_required(env):
    """Сделка из плана рождается СРАЗУ на «МП Отправлено» (владелец 13.09.2026).

    «Подготовка МП» — это стадия сделки, у которой плана ещё нет. Здесь он есть с первой
    секунды, поэтому проходить её не через что. Прибор ловит возврат промежуточной
    ступени: если сделка снова начнёт рождаться на первой стадии и ждать чьей-то отметки,
    тест покажет это сразу.
    """
    db, plan = env.db, env.mk()
    out = mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)

    deal = db.query(SalesDeal).filter(SalesDeal.id == out['deal_id']).first()
    assert deal is not None and deal.code, 'сделка без метки — по ней не сослаться'
    assert deal.our_stage_id == mp._mp_sent_stage(Catalog(db)).id, (
        'сделка из готового плана застряла на «Подготовка МП» — вернулась снятая ступень')
    assert deal.our_stage_id != env.first.id
    assert deal.bitrix_id.startswith('local-')


def test_the_birth_stage_is_recorded_in_history(env):
    """Первая постановка стадии пишется в историю (`from_stage_id` NULL).

    Без этой строки «сколько сделка стоит на стадии» считать не от чего, и правило
    срочности по рождённым из плана сделкам молча не срабатывает.
    """
    from app.sales.models import SalesDealStageHistory
    db, plan = env.db, env.mk()
    out = mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    rows = (db.query(SalesDealStageHistory)
            .filter(SalesDealStageHistory.deal_id == out['deal_id']).all())
    assert len(rows) == 1, 'рождение стадии не записано или записано дважды'
    assert rows[0].from_stage_id is None
    assert rows[0].to_stage_id == mp._mp_sent_stage(Catalog(db)).id


def test_the_deal_carries_the_plan(env):
    """Реквизиты, сумма и период — из плана; ответственный переведён user → SalesRep."""
    db, plan = env.db, env.mk()
    out = mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    deal = db.query(SalesDeal).filter(SalesDeal.id == out['deal_id']).first()

    assert (deal.advertiser_id, deal.brand_id) == (plan.advertiser_id, plan.brand_id)
    assert (deal.amount, deal.amount_with_vat) == (plan.amount_net, plan.amount_gross)
    assert deal.period_from.strftime('%Y-%m') == '2026-10'
    assert deal.product == 'Спецпроект', 'услуга сделки — первая строка размещения'
    assert deal.sales_rep_id == env.rep.id, (
        'ответственный не переведён: у плана id пользователя, у сделки id SalesRep')


def test_the_title_follows_the_conveyor_template(env):
    """Имя собирается как у конвейера: «Рекламодатель · Бренд · Услуга · Период»."""
    db, plan = env.db, env.mk()
    out = mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    parts = out['title'].split(' · ')
    assert parts[-1] == '2026-10' and parts[-2] == 'Спецпроект', out['title']
    assert env.brand.name in parts, out['title']


def test_the_link_reaches_every_version(env):
    """Привязка пишется во все версии группы — иначе следующая родится без сделки."""
    db, plan = env.db, env.mk()
    older = SalesMediaPlan(title=TITLE, version=2, group_id=plan.group_id,
                           advertiser_id=plan.advertiser_id, period='2026-10',
                           amount_net=1, amount_gross=1, created_by=env.actor.id)
    db.add(older)
    db.commit()

    out = mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    linked = {p.deal_id for p in db.query(SalesMediaPlan)
              .filter(SalesMediaPlan.group_id == plan.group_id).all()}
    assert linked == {out['deal_id']}, linked


def test_a_second_deal_is_refused(env):
    """У плана одна сделка. Вторая кнопка «Создать» — это дубль в реестре."""
    db, plan = env.db, env.mk()
    mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    with pytest.raises(HTTPException) as e:
        mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    assert e.value.status_code == 409


@pytest.mark.parametrize('broken, code, why', [
    ({'period': None}, 400, 'без периода не посчитать ни старт, ни срочность'),
    ({'advertiser_id': None, 'brand_id': None}, 400, 'сделка без стороны сделки'),
    # Пустой план — это план БЕЗ СТРОК; нулевая сумма при строках законна (100 % скидка,
    # владелец 24.09.2026) — её держит test_month_and_zero_plan.
    ({'_rows': False}, 400, 'план без строк — сделка-призрак'),
])
def test_incomplete_plans_are_refused(env, broken, code, why):
    """Пустой план не должен порождать сделку-призрак: её потом никто не опознает."""
    db, plan = env.db, env.mk(**broken)
    with pytest.raises(HTTPException) as e:
        mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    assert e.value.status_code == code, why


def test_attaching_a_plan_moves_a_deal_off_the_first_stage(env):
    """Второй путь: сделка уже была, аккаунт прикрепил к ней план — она двинулась.

    Это и есть граница «Подготовка МП» → «МП Отправлено» (владелец 13.09.2026): её
    держит факт связи, а не отметка в конструкторе. Прибор ловит возврат прежнего
    поведения, при котором прикрепление стадию не трогало.
    """
    db, plan = env.db, env.mk()
    deal = SalesDeal(bitrix_id='local-test-link', title='[тест] сделка сейлза',
                     pipeline='', bitrix_stage='', our_stage_id=env.first.id)
    db.add(deal)
    db.flush()

    plan.deal_id = deal.id
    mp._advance_deal_on_link(db, env.actor, plan)
    db.commit()
    db.refresh(deal)
    assert deal.our_stage_id == mp._mp_sent_stage(Catalog(db)).id


def test_a_deal_already_further_is_not_dragged_back(env):
    """Перепривязка плана к ушедшей вперёд сделке её не откатывает и не перепрыгивает."""
    db, plan = env.db, env.mk()
    out = mp.create_deal_from_plan(plan.id, mp.CreateDealIn(), db, env.actor)
    deal = db.query(SalesDeal).filter(SalesDeal.id == out['deal_id']).first()
    booked = mp._mp_sent_stage(Catalog(db))
    deal.our_stage_id = booked.id
    db.flush()

    mp._advance_deal_on_link(db, env.actor, plan)
    db.commit()
    db.refresh(deal)
    assert deal.our_stage_id == booked.id
