"""Отправка в ОРД: проверяется поведение вокруг НЕОБРАТИМОСТИ, а не счастливый путь.

Запись в ЕРИР не отзывается. Поэтому здесь закреплено ровно то, что защищает от дубля
и от отправки не туда:

  · след попытки существует ДО запроса — иначе потерянный ответ не с чем сопоставить;
  · обрыв связи НЕ закрывает попытку — «неизвестно» это не «не создалось»;
  · незавершённая попытка блокирует повтор;
  · проверки идут до журнала и до сети — отказ на входе не оставляет следов;
  · боевая запись требует отдельного разрешения, а не одного лишь ORD_ENV=prod.

Тесты идут на живой базе с фиктивными записями (тот же приём, что в соседних
test_ord_*.py), транспорт подменяется — до настоящего ОРД ни один тест не доходит.
"""
from datetime import date

import pytest

from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.ord import client as ord_client
from app.ord import submit
from app.ord.models import OrdSubmission

PREFIX = 'CTsubmit'
TEST_INN = '7700000081'


@pytest.fixture
def db():
    session = SessionLocal()
    clash = session.query(Counterparty.inn).filter(Counterparty.inn == TEST_INN).all()
    assert not clash, f"фиктивный ИНН {TEST_INN} занят реальным контрагентом"
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _purge(session):
    session.rollback()
    ids = [c.id for c in session.query(Contract)
           .filter(Contract.contract_number.like(f'{PREFIX}%')).all()]
    if ids:
        session.query(OrdSubmission).filter(
            OrdSubmission.kind == 'final_contract',
            OrdSubmission.local_id.in_(ids)).delete(synchronize_session=False)
        session.query(Contract).filter(Contract.id.in_(ids)).delete(synchronize_session=False)
    session.query(Counterparty).filter(Counterparty.inn == TEST_INN
                                       ).delete(synchronize_session=False)
    session.commit()


def _setup(session, *, ord_client_id='CT-client-1', client_env='demo'):
    cp = Counterparty(name=f'{PREFIX} Плательщик', inn=TEST_INN, status='действующий',
                      ord_client_id=ord_client_id, ord_env=client_env if ord_client_id else None)
    session.add(cp)
    session.flush()
    contract = Contract(counterparty_id=cp.id, counterparty_name=cp.name, inn=cp.inn,
                        contract_number=f'{PREFIX}-01', contract_date=date(2026, 1, 15),
                        payment_term_days=60, payment_term_condition='С даты УПД')
    session.add(contract)
    session.flush()
    session.commit()
    return cp, contract


@pytest.fixture
def user(db):
    from app.models import User
    return db.query(User).first()


@pytest.fixture(autouse=True)
def demo_contour(monkeypatch):
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.delenv('ORD_ALLOW_PROD_WRITE', raising=False)


def test_successful_registration_stores_id_and_contour(db, user, monkeypatch):
    cp, contract = _setup(db)
    monkeypatch.setattr(ord_client, 'post',
                        lambda path, body: (200, {'id': 'CT-final-77', 'status': 'Created'}))

    result = submit.register_final_contract(db, contract, user)

    db.refresh(contract)
    assert result['ord_id'] == 'CT-final-77'
    assert contract.ord_contract_id == 'CT-final-77'
    assert contract.ord_kind == 'final'
    assert contract.ord_env == 'demo', "контур обязан ехать вместе с идентификатором"
    row = db.query(OrdSubmission).filter(OrdSubmission.local_id == contract.id).one()
    assert row.finished_at is not None and row.ord_id == 'CT-final-77'
    assert row.request and row.request.get('clientId') == 'CT-client-1', (
        "тело запроса обязано сохраниться: без него отказ ОРД не разобрать")


def test_attempt_is_logged_before_the_request(db, user, monkeypatch):
    """След попытки существует уже в момент запроса, а не появляется после ответа.

    Иначе падение процесса между отправкой и ответом не оставило бы ничего, и повтор
    создал бы в ЕРИР дубль.
    """
    cp, contract = _setup(db)
    seen = {}

    def _post(path, body):
        other = SessionLocal()
        try:
            seen['rows'] = (other.query(OrdSubmission)
                            .filter(OrdSubmission.local_id == contract.id).count())
        finally:
            other.close()
        return (200, {'id': 'CT-final-78', 'status': 'Created'})

    monkeypatch.setattr(ord_client, 'post', _post)
    submit.register_final_contract(db, contract, user)

    assert seen['rows'] == 1, (
        "в момент запроса строка журнала должна быть уже зафиксирована в БД")


def test_network_break_leaves_attempt_open_and_blocks_repeat(db, user, monkeypatch):
    """Обрыв связи — это «неизвестно», а не «не создалось».

    Попытка остаётся незакрытой и блокирует повтор: запись в ЕРИР могла создаться, и
    второй запрос дал бы дубль, который не отозвать.
    """
    cp, contract = _setup(db)

    def _boom(path, body):
        raise ConnectionError('соединение разорвано')

    monkeypatch.setattr(ord_client, 'post', _boom)
    with pytest.raises(ConnectionError):
        submit.register_final_contract(db, contract, user)

    db.refresh(contract)
    assert contract.ord_contract_id is None
    row = db.query(OrdSubmission).filter(OrdSubmission.local_id == contract.id).one()
    assert row.finished_at is None, "обрыв не закрывает попытку"

    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: (200, {'id': 'CT-should-not-happen', 'status': 'Created'}))
    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_final_contract(db, contract, user)
    assert 'не завершилась' in str(e.value)


def test_ord_refusal_closes_attempt_and_allows_retry(db, user, monkeypatch):
    """Отказ ОРД — это ответ: запись не создалась, повтор после починки разрешён."""
    cp, contract = _setup(db)

    def _refuse(path, body):
        raise ord_client.OrdError(400, 'ОРД отклонил запрос — number: обязательное поле')

    monkeypatch.setattr(ord_client, 'post', _refuse)
    with pytest.raises(ord_client.OrdError):
        submit.register_final_contract(db, contract, user)

    row = db.query(OrdSubmission).filter(OrdSubmission.local_id == contract.id).one()
    assert row.finished_at is not None, "отказ закрывает попытку"
    assert 'обязательное поле' in (row.error or '')
    assert submit.pending(db, 'final_contract', contract.id, 'demo') is None


def test_already_registered_contract_is_refused_without_touching_ord(db, user, monkeypatch):
    cp, contract = _setup(db)
    contract.ord_contract_id = 'CT-already'
    contract.ord_env = 'demo'
    db.commit()
    called = []
    monkeypatch.setattr(ord_client, 'post', lambda p, b: called.append(1))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_final_contract(db, contract, user)

    assert 'уже зарегистрирован' in str(e.value)
    assert not called, "до ОРД запрос доходить не должен"
    assert db.query(OrdSubmission).filter(OrdSubmission.local_id == contract.id).count() == 0, (
        "отказ на входе не оставляет следов в журнале")


def test_missing_client_id_is_refused_before_any_call(db, user, monkeypatch):
    """Без идентификатора юрлица отправлять нечего — и это видно до запроса."""
    cp, contract = _setup(db, ord_client_id=None)
    called = []
    monkeypatch.setattr(ord_client, 'post', lambda p, b: called.append(1))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_final_contract(db, contract, user)

    assert 'идентификатора юрлица' in str(e.value)
    assert not called


def test_client_id_from_another_contour_is_refused(db, user, monkeypatch):
    """Идентификатор с прода при отправке на демо — ссылка в никуда."""
    cp, contract = _setup(db, ord_client_id='CT-prod-1', client_env='prod')
    called = []
    monkeypatch.setattr(ord_client, 'post', lambda p, b: called.append(1))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_final_contract(db, contract, user)

    assert 'контуров не общие' in str(e.value)
    assert not called


def test_prod_write_needs_its_own_permission(db, user, monkeypatch):
    """Одного ORD_ENV=prod мало: читать прод безопасно, писать — необратимо."""
    cp, contract = _setup(db, client_env='prod')
    monkeypatch.setattr(ord_client, 'env', lambda: 'prod')
    called = []
    monkeypatch.setattr(ord_client, 'post', lambda p, b: called.append(1))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_final_contract(db, contract, user)
    assert 'ORD_ALLOW_PROD_WRITE' in str(e.value)
    assert not called

    monkeypatch.setenv('ORD_ALLOW_PROD_WRITE', '1')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: (200, {'id': 'CT-prod-final', 'status': 'Created'}))
    submit.register_final_contract(db, contract, user)
    db.refresh(contract)
    assert contract.ord_env == 'prod'
