# -*- coding: utf-8 -*-
"""Сумма сделки берётся из привязанного медиаплана.

Правило владельца 31.08.2026: при наличии нашего МП с посчитанной суммой реестр, дашборд
и карточка показывают сумму ИЗ него, а не `deal.amount` (значение Битрикса). Прибор держит
и обратный край: заведённая и брошенная болванка БЕЗ СТРОК размещения сделку НЕ обнуляет.

Признак «план посчитан» — строки, а не ненулевой итог (правка 15.09.2026 по жалобе на
сделку MHNZUT): услуга со стопроцентной скидкой даёт посчитанный план на нулевую сумму,
и по итогу его не отличить от пустого.
"""
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.notify import models as _n  # noqa: F401
from app.ord import models as _o     # noqa: F401
from app.sales.models import SalesDeal, SalesMediaPlan, SalesMediaPlanRow
from app.sales.mp_amounts import eff_gross, eff_net, mp_amounts_by_deal

NO = 990000  # номера-версии МП теста — заведомо выше рабочих group_id теста


def _d(id, amount, wv=None):
    return SimpleNamespace(id=id, amount=amount, amount_with_vat=wv)


# ── чистые функции: из МП, если он есть; иначе из сделки ─────────────────────
def test_eff_prefers_mp_over_deal():
    mp = {1: (500000.0, 610000.0)}
    assert eff_net(_d(1, 999.0), mp) == 500000.0        # МП, не сделка
    assert eff_gross(_d(1, 999.0, 111.0), mp) == 610000.0
    # у сделки без МП — своя сумма
    assert eff_net(_d(2, 777.0), mp) == 777.0
    assert eff_gross(_d(2, 777.0, 900.0), mp) == 900.0


# ── сборка по базе: старшая версия, пустой не обнуляет ──────────────────────
@pytest.fixture()
def env():
    db = SessionLocal()
    made = []
    # Сделка берётся ДЕТЕРМИНИРОВАННО и обязательно БЕЗ своих медиапланов.
    #
    # Без `order_by` `.first()` отдаёт строку в физическом порядке кучи, а он меняется от
    # любого UPDATE в таблице: правка ответственного на СОСЕДНЕЙ сделке 04.09.2026
    # переставила порядок, тест взял другую сделку — с настоящим МП на 25 000, — и все
    # четыре проверки упали с ровным смещением. Выглядело как поломка расчёта суммы,
    # хотя расчёт был цел. Условие «без медиапланов» закрывает вторую половину: чужой МП
    # складывается с тестовым, и сумма перестаёт быть предсказуемой.
    has_mp = (db.query(SalesMediaPlan.id)
              .filter(SalesMediaPlan.deal_id == SalesDeal.id).exists())
    deal = (db.query(SalesDeal)
            .filter(SalesDeal.amount.isnot(None), ~has_mp)
            .order_by(SalesDeal.id).first())
    if not deal:
        db.close()
        pytest.skip('нужна сделка с суммой и без медиапланов')
    # чистим свои артефакты и до теста (мусор от упавшего прогона)
    db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id >= NO).delete()
    db.commit()
    yield SimpleNamespace(db=db, deal=deal, made=made)
    db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id >= NO).delete()
    db.commit()
    db.close()


def _mp(env, group, version, net, gross, deal_id, rows=1):
    """Медиаплан теста. rows=0 — болванка без размещений, то есть «план не заводили»."""
    p = SalesMediaPlan(title='[тест] сумма', group_id=group, version=version,
                       amount_net=net, amount_gross=gross, deal_id=deal_id)
    env.db.add(p)
    env.db.commit()
    for i in range(rows):
        env.db.add(SalesMediaPlanRow(plan_id=p.id, sort_order=i, position='[тест]',
                                     model='CPM', volume=1000, unit_price=0))
    env.db.commit()
    return p


def test_amount_comes_from_calculated_mp(env):
    _mp(env, NO, 1, 500000, 610000, env.deal.id)
    got = mp_amounts_by_deal(env.db, [env.deal.id])
    assert got.get(env.deal.id) == (500000.0, 610000.0)
    assert eff_net(env.deal, got) == 500000.0


def test_latest_version_wins(env):
    _mp(env, NO, 1, 100000, 122000, env.deal.id)
    _mp(env, NO, 2, 700000, 854000, env.deal.id)   # старшая версия той же группы
    got = mp_amounts_by_deal(env.db, [env.deal.id])
    assert got[env.deal.id] == (700000.0, 854000.0)


def test_a_plan_without_rows_does_not_zero_the_deal(env):
    """Болванка: план завели, размещений не внесли. Сумма остаётся битриксовой."""
    _mp(env, NO, 1, 0, 0, env.deal.id, rows=0)
    got = mp_amounts_by_deal(env.db, [env.deal.id])
    assert env.deal.id not in got                  # в словаре его нет
    assert eff_net(env.deal, got) == float(env.deal.amount)   # сумма сделки, не 0


def test_a_calculated_plan_worth_zero_wins_over_bitrix(env):
    """Стопроцентная скидка: план посчитан, итог ноль — и сделка стоит ноль.

    Сделка MHNZUT (жалоба владельца 15.09.2026): услуга отдана со стопроцентной скидкой,
    а реестр показывал 372 000 из Битрикса. Цена Битрикса — ориентир аккаунту при сборке
    плана; как только план привязан, цена только из него.
    """
    _mp(env, NO, 1, 0, 0, env.deal.id, rows=1)
    got = mp_amounts_by_deal(env.db, [env.deal.id])
    assert got[env.deal.id] == (0.0, 0.0)
    assert eff_net(env.deal, got) == 0.0
    assert eff_gross(env.deal, got) == 0.0


def test_two_groups_are_summed(env):
    _mp(env, NO, 1, 300000, 366000, env.deal.id)
    _mp(env, NO + 1, 1, 200000, 244000, env.deal.id)
    got = mp_amounts_by_deal(env.db, [env.deal.id])
    assert got[env.deal.id] == (500000.0, 610000.0)
