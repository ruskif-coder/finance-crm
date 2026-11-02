# -*- coding: utf-8 -*-
"""План оплат — короткий список «что платить в это окно», который человек собирает сам.

Решение владельца 02.11.2026: это ОТМЕТКА на операции (`operations.pay_plan_at`), а не
статус. Статус «ПЛАН ОПЛАТ» — кредиторка, его читают отчёты; ставить его ради списка
значило бы смешать долг с намерением платить.

Поломки, которые тест ловит:
  · оплаченная операция осталась в плане — путей в «ОПЛАЧЕНО» четыре (форма, массовая
    правка, частичная оплата, импорт), и снятие отметки обязано стоять на ВСЕХ, то есть
    в модели, а не в одной из ручек;
  · в план встало то, что платить не нужно (поступление, уже оплаченное);
  · вкладка показывает не план, а весь реестр.
"""
from datetime import date

import pytest

from app.database import SessionLocal
from app.models import Article, Operation, User
from app.routers import operation_chains as chains_router
from app.routers import operations as ops


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
def user(db):
    return db.query(User).order_by(User.id).first()


def _op(db, **kw):
    art = db.query(Article).order_by(Article.id).first()
    row = dict(date=date(2026, 11, 2), status="ПЛАН ОПЛАТ", income=0.0, expense=1000.0,
               bank="АльфаБанк", period="2026-11", article_id=art.id)
    row.update(kw)
    o = Operation(**row)
    db.add(o)
    db.flush()
    return o


def _plan_ids(db, user):
    res = ops.get_operations(pay_plan=True, limit=100000, status=None, bank=None, date_from=None,
                             date_to=None, article_id=None, counterparty_id=None, period=None,
                             op_type=None, gaps=None, ids=None, sort_col="date", sort_dir="desc",
                             db=db, current_user=user)
    return {r["id"] for r in res["items"]}


def test_only_unpaid_expenses_go_into_the_plan(db, user):
    debt = _op(db)
    paid = _op(db, status="ОПЛАЧЕНО")
    incoming = _op(db, status="ПЛАН ПОСТУПЛЕНИЙ", income=500.0, expense=0.0)

    res = ops.add_to_pay_plan(ops.PayPlanIds(ids=[debt.id, paid.id, incoming.id]), db=db,
                              current_user=user)

    assert res["added"] == 1
    assert res["skipped"] == 2
    assert debt.pay_plan_at is not None and debt.pay_plan_by == user.id
    assert paid.pay_plan_at is None and incoming.pay_plan_at is None


def test_the_tab_shows_the_plan_and_not_the_registry(db, user):
    planned, other = _op(db), _op(db)
    ops.add_to_pay_plan(ops.PayPlanIds(ids=[planned.id]), db=db, current_user=user)

    got = _plan_ids(db, user)

    assert planned.id in got
    assert other.id not in got
    row = next(r for r in ops.get_operations(
        ids=[planned.id, other.id], pay_plan=False, limit=10, status=None, bank=None,
        date_from=None, date_to=None, article_id=None, counterparty_id=None, period=None,
        op_type=None, gaps=None, sort_col="date", sort_dir="desc", db=db,
        current_user=user)["items"] if r["id"] == planned.id)
    assert row["pay_plan"] is True


def test_removed_by_hand_leaves_the_plan(db, user):
    o = _op(db)
    ops.add_to_pay_plan(ops.PayPlanIds(ids=[o.id]), db=db, current_user=user)

    ops.remove_from_pay_plan(ops.PayPlanIds(ids=[o.id]), db=db, current_user=user)

    assert o.pay_plan_at is None
    assert o.id not in _plan_ids(db, user)


def _pay_by_form(db, user, o):
    ops.update_operation(o.id, ops.OperationCreate(status="ОПЛАЧЕНО"), db=db, current_user=user)


def _pay_by_bulk(db, user, o):
    ops.bulk_update_operations(ops.OperationBulkUpdate(ids=[o.id], status="ОПЛАЧЕНО"), db=db,
                               current_user=user)


def _pay_by_partial_payment_of_the_rest(db, user, o):
    chains_router.partial_payment(o.id, chains_router.PartialPaymentIn(
        amount=1000.0, date=date(2026, 11, 2), bank="АльфаБанк"), db=db, current_user=user)


def _pay_by_import(db, user, o):
    o.status = "ОПЛАЧЕНО"     # импорт-синхронизация пишет статус в существующую строку так
    db.flush()


@pytest.mark.parametrize("pay", [_pay_by_form, _pay_by_bulk, _pay_by_partial_payment_of_the_rest,
                                 _pay_by_import])
def test_paid_leaves_the_plan_on_every_path(db, user, pay):
    o = _op(db)
    ops.add_to_pay_plan(ops.PayPlanIds(ids=[o.id]), db=db, current_user=user)

    pay(db, user, o)

    db.refresh(o)
    assert o.status == "ОПЛАЧЕНО"
    assert o.pay_plan_at is None
    assert o.id not in _plan_ids(db, user)


def test_a_partial_payment_keeps_the_rest_in_the_plan(db, user):
    """Оплатили часть — остаток ещё платить, он остаётся в окне; оплаченная часть в план не попадает."""
    o = _op(db)
    ops.add_to_pay_plan(ops.PayPlanIds(ids=[o.id]), db=db, current_user=user)

    res = chains_router.partial_payment(o.id, chains_router.PartialPaymentIn(
        amount=400.0, date=date(2026, 11, 2), bank="АльфаБанк"), db=db, current_user=user)

    got = _plan_ids(db, user)
    assert o.id in got
    assert res["part_id"] not in got
