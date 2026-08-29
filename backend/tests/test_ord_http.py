"""
Эндпоинты обвязки ОРД.

Проверяется форма ответа `assembly` — на нём стоит весь экран сборки, и молчаливое
переименование ключа сломает цепочку гейтов без единой ошибки в логах.

Находка ревью I5, 25.08.2026: до этого файл не проверял ничего. `ASSEMBLY_KEYS` и
`STEP_FIELDS` объявлены в routers/ord.py, но самим эндпоинтом не читаются — ответ
`deal_assembly` собирается литералом, — так что сравнение констант со своими же
значениями (`ASSEMBLY_KEYS == ('payer', 'final', 'initial', 'creatives')`) не ловило
бы переименование ключа в РЕАЛЬНОМ ответе. А `test_binding_endpoint_exists_and_is_gated`
проверял `hasattr(ord_router, 'bind_initial')` — это истинно для любой функции с таким
именем независимо от того, что стоит в её `Depends()`, то есть не проверяло гейт вовсе.

Здесь — фактический ответ `deal_assembly` на реальной сделке (тот же приём фиктивного
admin-пользователя, что и в test_ord_matching.py) и поведенческая проверка гейта
`bind_initial`: зависимость достаётся из сигнатуры эндпоинта и вызывается напрямую с
пользователем, у роли которого сначала нет, а потом есть право `sales_registry.edit`.
"""
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Contract, Counterparty, Role, RolePermission, User
from app.routers import ord as ord_router
from app.sales.models import SalesDeal

TEST_ORD_PREFIX = 'HTTPtest'
TEST_INN = '7700000041'

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'))


def _purge(db):
    """Снести сделку/договор/контрагента/роль-и-пользователя этого файла.

    Вызывается и до, и после теста — до ловит мусор прошлого упавшего прогона,
    после убирает свой собственный (тот же приём, что в соседних test_ord_*.py).
    Порядок важен: User и RolePermission ссылаются на Role внешним ключом.
    """
    db.rollback()
    db.query(SalesDeal).filter(
        SalesDeal.bitrix_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    db.query(Contract).filter(
        Contract.ord_contract_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    db.query(Counterparty).filter(Counterparty.inn == TEST_INN).delete(synchronize_session=False)
    db.query(User).filter(User.email.like(f'{TEST_ORD_PREFIX}%')).delete(synchronize_session=False)
    role_ids = [r.id for r in db.query(Role.id)
               .filter(Role.key.like(f'{TEST_ORD_PREFIX}%')).all()]
    if role_ids:
        db.query(RolePermission).filter(
            RolePermission.role_id.in_(role_ids)
        ).delete(synchronize_session=False)
        db.query(Role).filter(Role.id.in_(role_ids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def db():
    """Настоящая сессия (app.database.SessionLocal) на рабочей базе.

    TEST_INN обязан не совпадать ни с одним реальным контрагентом — иначе
    deal_assembly резолвил бы плательщику этого теста боевой договор вместо
    фиктивной строки, которую заводит сам тест. Проверка идёт ДО очистки (находка
    I6 в соседних test_ord_matching.py/test_ord_import.py — «сначала почистить,
    потом проверить» гарантированно не находит клэша, даже если он был).
    """
    session = SessionLocal()
    clash = session.query(Counterparty.inn).filter(Counterparty.inn == TEST_INN).all()
    assert not clash, f"фиктивный ИНН {TEST_INN} занят реальным контрагентом {clash}"
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _make_deal(db):
    """Сделка с однозначно резолвящимся плательщиком и доходным договором —
    достаточно, чтобы ступени «Плательщик» и «Доходный договор» вышли ok=True с
    настоящими, а не пустыми значениями."""
    cp = Counterparty(name=f'{TEST_ORD_PREFIX} Плательщик', inn=TEST_INN)
    db.add(cp)
    db.flush()
    contract = Contract(counterparty_id=cp.id, ord_contract_id=f'{TEST_ORD_PREFIX}-final-1',
                        ord_kind='final', contract_number='ТД-HTTP-1/2026')
    db.add(contract)
    db.flush()
    deal = SalesDeal(bitrix_id=f'{TEST_ORD_PREFIX}-deal-1', payer_counterparty_id=cp.id)
    db.add(deal)
    db.flush()
    return deal


def test_assembly_response_has_the_four_pinned_steps_with_required_fields(db):
    """Форма ответа — контракт с экраном: реальный JSON deal_assembly несёт все
    четыре ключа ASSEMBLY_KEYS, и на каждой ступени есть title/ok/reason
    (STEP_FIELDS), причём `ok` — именно bool, не строка и не None (экран решает
    по нему, рисовать ли галочку).
    """
    deal = _make_deal(db)
    result = ord_router.deal_assembly(deal.id, db=db, current_user=_FAKE_ADMIN)

    assert set(ord_router.ASSEMBLY_KEYS) <= set(result.keys()), (
        f"в реальном ответе нет одной из ступеней ASSEMBLY_KEYS: {result.keys()}"
    )
    for key in ord_router.ASSEMBLY_KEYS:
        step = result[key]
        for field in ord_router.STEP_FIELDS:
            assert field in step, f"ступень «{key}» лишилась поля «{field}»: {step}"
        assert isinstance(step['ok'], bool), f"«{key}».ok не bool — {step['ok']!r}"


def test_assembly_reflects_the_resolved_deal_not_a_hollow_shape(db):
    """Мало наличия полей — сами значения обязаны отражать РЕАЛЬНУЮ сделку: без
    этого проверка формы прошла бы и на ответе, где всё ok=False, reason='',
    contract=None — то есть на пустышке правильной формы.
    """
    deal = _make_deal(db)
    result = ord_router.deal_assembly(deal.id, db=db, current_user=_FAKE_ADMIN)

    assert result['payer']['ok'] is True
    assert result['payer']['name'] == f'{TEST_ORD_PREFIX} Плательщик'
    assert result['final']['ok'] is True
    assert result['final']['contract']['number'] == 'ТД-HTTP-1/2026'
    # Ещё не привязано — но обоснование обязано быть непустым уже на этой ступени
    # (реальных кандидатов у сделки нет, реакция — понятный отказ, не тишина).
    assert result['initial']['reason']


def _permission_checker(endpoint_fn, param='current_user'):
    """Достаёт функцию-гейт из Depends() эндпоинта — тот же приём, каким сам
    FastAPI разрешает зависимости, только напрямую, без HTTP-запроса вокруг.
    `Depends(dependency)` — это то же самое, что стоит в сигнатуре по умолчанию,
    поэтому объект здесь ровно тот, что реально обслуживает запросы.
    """
    default = inspect.signature(endpoint_fn).parameters[param].default
    return default.dependency


def test_binding_endpoint_is_gated_by_sales_registry_edit(db):
    """Привязка — запись, значит нужно право edit на sales_registry, а не только
    view и не право на что-то ещё. Старый тест проверял hasattr(ord_router,
    'bind_initial') — это истинно для любой функции с таким именем независимо от
    Depends(), то есть ловит только переименование функции, не подмену права на
    более слабое. Здесь — поведенческая проверка: тот же гейт, что реально висит
    на эндпоинте, вызывается напрямую на пользователе без права и с правом.
    """
    checker = _permission_checker(ord_router.bind_initial)

    role = Role(key=f'{TEST_ORD_PREFIX}_role', label=f'{TEST_ORD_PREFIX} viewer-only')
    db.add(role)
    db.flush()
    perm = RolePermission(role_id=role.id, section='sales_registry', can_view=1, can_edit=0)
    db.add(perm)
    db.flush()
    user = User(name='t', email=f'{TEST_ORD_PREFIX}@test.invalid',
               hashed_password='x', role_id=role.id)
    db.add(user)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        checker(current_user=user, db=db)
    assert exc.value.status_code == 403, (
        "право view на sales_registry пропустило привязку — привязка не должна "
        "требовать меньше, чем edit"
    )

    perm.can_edit = 1
    db.flush()
    assert checker(current_user=user, db=db) is user, (
        "с правом edit на sales_registry гейт всё равно не пропускает — "
        "проверка не на том разделе/действии"
    )
