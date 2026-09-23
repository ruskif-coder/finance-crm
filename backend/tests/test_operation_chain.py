# -*- coding: utf-8 -*-
"""Прибор: цепочка частичных оплат — материнская операция и её части.

Решение владельца 23.09.2026. Частичное закрытие плановой операции — это ОДНО действие
«Частичная оплата»: сервер создаёт оплаченную часть со ссылкой на материнскую и
уменьшает остаток у материнской. Раньше это делали руками — копия, правка двух сумм, —
и в данных оставались несвязанные операции с одинаковыми № ДС и Счётом (аудит
23.09.2026, 2.H1).

Правила, которые здесь держатся:
  · ссылка всегда на КОРЕНЬ цепочки — цепочка плоская;
  · сумма договора = материнская + все части, ни копейкой не теряется при делении;
  · оплата ровно на остаток закрывает саму материнскую, новой части не появляется;
  · материнскую с частями обычным удалением не удалить — только принудительно, с паролем;
  · часть можно отвязать.

Ручки вызываются напрямую, в транзакции с откатом.
"""
from datetime import date

import pytest
from fastapi import HTTPException

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import Article, Operation, Role, User
from app.passwords import hash_password
from app.routers import operation_chains as oc
from app.routers import operations as ops

PWD = "прибор-цепочки-7"


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush          # всё, что записали ручки, откатывается в конце
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def user(db):
    """Своя учётка с известным паролем — чужие пароли прибору знать неоткуда."""
    role = db.query(Role).filter(Role.key == "admin").first()
    u = User(email="chain-probe@example.invalid", name="прибор цепочки",
             hashed_password=hash_password(PWD), role_id=role.id, is_active=1)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def plan(db, user):
    art = db.query(Article).order_by(Article.id).first()
    op = Operation(date=date(2099, 1, 10), status="ПЛАН ПОСТУПЛЕНИЙ", income=1000.0,
                   expense=0.0, bank="АльфаБанк", period="2099-01", vat_rate=22,
                   vat_fact=ops.compute_vat_fact(1000.0, 0, 22), article_id=art.id,
                   ds_num="прибор 1", invoice="999", created_by=user.id)
    db.add(op)
    db.flush()
    return op


def _pay(db, user, op_id, amount, **kw):
    body = oc.PartialPaymentIn(amount=amount, date=kw.get("date", date(2099, 1, 20)),
                               bank=kw.get("bank"))
    return oc.partial_payment(op_id, body, db=db, current_user=user)


def _get(db, op_id):
    return db.query(Operation).filter(Operation.id == op_id).first()


# ── Частичная оплата ─────────────────────────────────────────────────────────────

def test_partial_payment_splits_the_plan(db, user, plan):
    res = _pay(db, user, plan.id, 300)
    part = _get(db, res["part_id"])
    root = _get(db, plan.id)
    assert (part.status, part.income, part.parent_operation_id) == ("ОПЛАЧЕНО", 300, plan.id)
    assert part.date == date(2099, 1, 20)
    assert (root.status, root.income) == ("ПЛАН ПОСТУПЛЕНИЙ", 700)
    # Реквизиты счёта переезжают в часть — по ним её потом узнают в выписке и импорте.
    assert (part.ds_num, part.invoice, part.article_id, part.period) == \
           (root.ds_num, root.invoice, root.article_id, root.period)
    # НДС пересчитан у обеих: сервер его считает, клиент не присылает.
    assert part.vat_fact == ops.compute_vat_fact(300, 0, 22)
    assert root.vat_fact == ops.compute_vat_fact(700, 0, 22)


def test_second_part_links_to_the_root_not_to_the_previous_part(db, user, plan):
    _pay(db, user, plan.id, 300)
    res = _pay(db, user, plan.id, 200)
    assert _get(db, res["part_id"]).parent_operation_id == plan.id
    assert _get(db, plan.id).income == 500


def test_no_kopeck_is_lost_in_the_split(db, user, plan):
    plan.income = 1000.10
    db.flush()
    _pay(db, user, plan.id, 333.33)
    _pay(db, user, plan.id, 333.33)
    parts = db.query(Operation).filter(Operation.parent_operation_id == plan.id).all()
    total = round(_get(db, plan.id).income + sum(p.income for p in parts), 2)
    assert total == 1000.10


def test_paying_the_exact_remainder_closes_the_mother_itself(db, user, plan):
    _pay(db, user, plan.id, 400)
    res = _pay(db, user, plan.id, 600, bank="ОПТ Банк")
    root = _get(db, plan.id)
    assert res.get("part_id") is None and res["closed"] is True
    assert (root.status, root.income, root.bank, root.date) == \
           ("ОПЛАЧЕНО", 600, "ОПТ Банк", date(2099, 1, 20))
    assert db.query(Operation).filter(Operation.parent_operation_id == plan.id).count() == 1


def test_expense_side_is_split_the_same_way(db, user, plan):
    plan.status, plan.income, plan.expense = "ПЛАН ОПЛАТ", 0.0, 500.0
    db.flush()
    res = _pay(db, user, plan.id, 125)
    assert _get(db, res["part_id"]).expense == 125
    assert _get(db, plan.id).expense == 375


@pytest.mark.parametrize("amount", [0, -5, 1000.01])
def test_amount_must_fit_the_remainder(db, user, plan, amount):
    with pytest.raises(HTTPException) as e:
        _pay(db, user, plan.id, amount)
    assert e.value.status_code == 400


def test_a_paid_operation_cannot_be_split(db, user, plan):
    plan.status = "ОПЛАЧЕНО"
    db.flush()
    with pytest.raises(HTTPException) as e:
        _pay(db, user, plan.id, 100)
    assert e.value.status_code == 400


def test_part_without_a_bank_is_refused(db, user, plan):
    plan.bank = None
    db.flush()
    with pytest.raises(HTTPException) as e:
        _pay(db, user, plan.id, 100)
    assert e.value.status_code == 400 and "банк" in e.value.detail.lower()


# ── Цепочка и отвязка ────────────────────────────────────────────────────────────

def test_chain_shows_the_mother_parts_and_the_contract_total(db, user, plan):
    _pay(db, user, plan.id, 300)
    part = _pay(db, user, plan.id, 200)["part_id"]
    for probe in (plan.id, part):            # спрашивать можно с любого звена
        ch = oc.get_chain(probe, db=db, current_user=user)
        assert ch["root"]["id"] == plan.id
        assert sorted(p["amount"] for p in ch["parts"]) == [200, 300]
        assert ch["total"] == 1000 and ch["paid"] == 500 and ch["remaining"] == 500


def test_a_part_can_be_unlinked(db, user, plan):
    part = _pay(db, user, plan.id, 300)["part_id"]
    oc.unlink_parent(part, db=db, current_user=user)
    assert _get(db, part).parent_operation_id is None


def test_registry_rows_carry_the_chain(db, user, plan):
    part = _pay(db, user, plan.id, 300)["part_id"]
    res = ops.get_operations(skip=0, limit=500, status=None, bank=None, article_id=None,
                             counterparty_id=None, period=None, gaps=None,
                             ids=[plan.id, part], db=db, current_user=user)
    by_id = {r["id"]: r for r in res["items"]}
    assert by_id[part]["parent_operation_id"] == plan.id
    assert by_id[plan.id]["parts_count"] == 1
    assert by_id[part]["parts_count"] == 0


# ── Удаление ─────────────────────────────────────────────────────────────────────

def test_mother_with_parts_is_not_deleted_by_plain_delete(db, user, plan):
    _pay(db, user, plan.id, 300)
    with pytest.raises(HTTPException) as e:
        ops.delete_operation(plan.id, db=db, current_user=user)
    assert e.value.status_code == 409
    assert _get(db, plan.id) is not None


def test_bulk_delete_refuses_a_mother_without_its_parts(db, user, plan):
    _pay(db, user, plan.id, 300)
    with pytest.raises(HTTPException) as e:
        ops.bulk_delete_operations(ops.OperationBulkDelete(ids=[plan.id]), db=db,
                                   current_user=user)
    assert e.value.status_code == 409


def test_bulk_delete_takes_the_whole_chain_at_once(db, user, plan):
    part = _pay(db, user, plan.id, 300)["part_id"]
    ops.bulk_delete_operations(ops.OperationBulkDelete(ids=[plan.id, part], password=PWD),
                               db=db, current_user=user)
    assert _get(db, plan.id) is None and _get(db, part) is None


def test_whole_chain_is_not_deleted_without_a_password(db, user, plan):
    """Решение владельца 23.09.2026: цепочка удаляется только с паролем — и одна материнская,
    и вся целиком. До этого удаление всей цепочки выделением шло без пароля, хотя стирает
    больше, чем защищённое паролем удаление одной материнской."""
    part = _pay(db, user, plan.id, 300)["part_id"]
    with pytest.raises(HTTPException) as e:
        ops.bulk_delete_operations(ops.OperationBulkDelete(ids=[plan.id, part]), db=db,
                                   current_user=user)
    assert e.value.status_code == 428 and e.value.detail["need_password"] is True
    with pytest.raises(HTTPException) as e:
        ops.bulk_delete_operations(ops.OperationBulkDelete(ids=[plan.id, part], password="не тот"),
                                   db=db, current_user=user)
    assert e.value.status_code == 403
    assert _get(db, plan.id) is not None and _get(db, part) is not None


def test_plain_bulk_delete_needs_no_password(db, user, plan):
    """Разовые операции и отдельные части — без пароля, как раньше."""
    part = _pay(db, user, plan.id, 300)["part_id"]
    ops.bulk_delete_operations(ops.OperationBulkDelete(ids=[part]), db=db, current_user=user)
    assert _get(db, part) is None


def test_force_delete_needs_the_right_password(db, user, plan):
    _pay(db, user, plan.id, 300)
    with pytest.raises(HTTPException) as e:
        oc.force_delete(plan.id, oc.ForceDeleteIn(password="не тот"), db=db,
                        current_user=user)
    assert e.value.status_code == 403
    assert _get(db, plan.id) is not None


def test_force_delete_leaves_the_parts_standalone(db, user, plan):
    part = _pay(db, user, plan.id, 300)["part_id"]
    oc.force_delete(plan.id, oc.ForceDeleteIn(password=PWD), db=db, current_user=user)
    db.expire_all()
    assert _get(db, plan.id) is None
    survivor = _get(db, part)
    assert survivor is not None and survivor.parent_operation_id is None


def test_a_part_is_deleted_as_usual(db, user, plan):
    part = _pay(db, user, plan.id, 300)["part_id"]
    ops.delete_operation(part, db=db, current_user=user)
    assert _get(db, part) is None


def test_partial_payment_needs_both_edit_and_create():
    """Материнская меняется (правка), часть заводится (создание) — нужны оба права."""
    route = next(r for r in oc.router.routes if r.path.endswith("/partial-payment"))
    need = {(d.call._perm_sections, d.call._perm_action)
            for d in route.dependant.dependencies if hasattr(d.call, "_perm_action")}
    assert {(("operations",), "edit"), (("operations",), "create")} <= need, need


def test_concurrent_partial_payment_waits_for_the_first(db, user):
    """Второй запрос ждёт первого, а не делит тот же остаток: строка читается под
    блокировкой. Здесь другое соединение держит строку, и запрос обязан упереться в
    ожидание. Операция заводится и КОММИТИТСЯ соседним соединением — иначе её не
    заблокировать, — и убирается в конце."""
    from sqlalchemy import exc, text

    from app.database import engine
    art = db.query(Article).order_by(Article.id).first()
    with engine.begin() as c:
        op_id = c.execute(text(
            "INSERT INTO operations (date, status, income, expense, bank, period, vat_rate, "
            "vat_fact, article_id, ds_num, invoice) VALUES ('2099-01-10', 'ПЛАН ПОСТУПЛЕНИЙ', "
            "1000, 0, 'АльфаБанк', '2099-01', 0, 0, :a, 'прибор гонки', '1') RETURNING id"),
            {"a": art.id}).scalar()
    try:
        with engine.connect() as other:
            tx = other.begin()
            other.execute(text("SELECT id FROM operations WHERE id = :i FOR UPDATE"), {"i": op_id})
            db.execute(text("SET LOCAL lock_timeout = '300ms'"))
            # Сумма больше остатка: без блокировки на ЧТЕНИИ запрос сразу отказал бы 400 по
            # остатку, прочитанному в обход соседа (так и делятся дважды), и до записи, где
            # ждать пришлось бы в любом случае, не дошёл бы. Ждать обязан уже на чтении.
            with pytest.raises(exc.OperationalError, match="lock timeout"):
                _pay(db, user, op_id, 5000)
            tx.rollback()
    finally:
        db.rollback()
        with engine.begin() as c:
            c.execute(text("DELETE FROM operations WHERE id = :i OR parent_operation_id = :i"),
                      {"i": op_id})


# ── Разметка существующих цепочек ────────────────────────────────────────────────

def _op(id_, status, amount, cp=1, ds="доп 2", inv="25", parent=None):
    from types import SimpleNamespace
    return SimpleNamespace(id=id_, status=status, income=amount, expense=0.0,
                           counterparty_id=cp, ds_num=ds, invoice=inv,
                           parent_operation_id=parent)


def test_backfill_roots_the_chain_at_the_remaining_plan():
    from app.operation_chains import plan_backfill
    got = plan_backfill([_op(10, "ОПЛАЧЕНО", 100), _op(11, "ОПЛАЧЕНО", 358),
                         _op(12, "ПЛАН ПОСТУПЛЕНИЙ", 458)])
    assert got["links"] == {10: 12, 11: 12} and not got["unclear"]


def test_backfill_roots_a_fully_paid_chain_at_the_first_operation():
    from app.operation_chains import plan_backfill
    got = plan_backfill([_op(21, "ОПЛАЧЕНО", 1), _op(20, "ОПЛАЧЕНО", 2)])
    assert got["links"] == {21: 20}


def test_backfill_never_joins_different_counterparties():
    from app.operation_chains import plan_backfill
    got = plan_backfill([_op(30, "ОПЛАЧЕНО", 1, cp=1), _op(31, "ОПЛАЧЕНО", 2, cp=2)])
    assert got["links"] == {}


def test_backfill_leaves_two_plans_for_a_human():
    from app.operation_chains import plan_backfill
    got = plan_backfill([_op(40, "ПЛАН ПОСТУПЛЕНИЙ", 1), _op(41, "ПЛАН ПОСТУПЛЕНИЙ", 2),
                         _op(42, "ОПЛАЧЕНО", 3)])
    assert got["links"] == {} and len(got["unclear"]) == 1


def test_backfill_does_not_touch_already_linked_groups():
    from app.operation_chains import plan_backfill
    got = plan_backfill([_op(50, "ОПЛАЧЕНО", 1, parent=51), _op(51, "ПЛАН ПОСТУПЛЕНИЙ", 2)])
    assert got["links"] == {}


def test_force_delete_password_is_not_a_free_bruteforce(db, user, plan):
    """Пять неверных паролей — та же блокировка, что у входа: шестая попытка получает 429
    даже с верным паролем (ревью 23.09.2026)."""
    _pay(db, user, plan.id, 300)
    for _ in range(5):
        with pytest.raises(HTTPException) as e:
            oc.force_delete(plan.id, oc.ForceDeleteIn(password="не тот"), db=db, current_user=user)
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        oc.force_delete(plan.id, oc.ForceDeleteIn(password=PWD), db=db, current_user=user)
    assert e.value.status_code == 429
    assert _get(db, plan.id) is not None
