"""Отправка в ОРД: проверяется поведение вокруг НЕОБРАТИМОСТИ, а не счастливый путь.

Запись в ЕРИР не отзывается. Поэтому здесь закреплено ровно то, что защищает от дубля
и от отправки не туда:

  · след попытки существует ДО запроса — иначе потерянный ответ не с чем сопоставить;
  · обрыв связи НЕ закрывает попытку — «неизвестно» это не «не создалось»;
  · незавершённая попытка блокирует повтор;
  · проверки идут до журнала и до сети — отказ на входе не оставляет следов;
  · боевая запись требует отдельного разрешения, а не одного лишь ORD_ENV=prod;
  · из зависшей попытки ЕСТЬ выход, и он не симметричен: «записи нет» открывает повтор,
    «запись есть» оставляет его закрытым.

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
    # попытки заведения юрлица — ключ по ИНН (`registry.client_key`)
    session.query(OrdSubmission).filter(
        OrdSubmission.kind == 'client',
        OrdSubmission.local_id == int(TEST_INN[:9])).delete(synchronize_session=False)
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


def test_missing_client_is_found_or_created_by_default(db, user, monkeypatch):
    """Регистрация доходного из справочника по умолчанию сама находит или заводит
    юрлицо плательщика — как регистрация изначального (владелец, 24.09.2026). Раньше
    без идентификатора был отказ «сначала сверка юрлиц», и новый договор с новым
    клиентом зарегистрировать было нельзя вовсе."""
    cp, contract = _setup(db, ord_client_id=None)
    posted = []

    def post(path, body):
        posted.append(path)
        if path == '/webapi/v3/clients':
            return 200, {'id': 'CL-new-payer', 'status': 'Active'}
        return 200, {'id': 'CT-final-88', 'status': 'Created'}
    monkeypatch.setattr(ord_client, 'get', lambda p, params=None: [])
    monkeypatch.setattr(ord_client, 'post', post)

    result = submit.register_final_contract(db, contract, user)

    db.refresh(cp)
    assert posted == ['/webapi/v3/clients', '/webapi/v3/contracts/final']
    assert result['ord_id'] == 'CT-final-88'
    assert cp.ord_client_id == 'CL-new-payer' and cp.ord_env == 'demo', (
        "найденное или заведённое юрлицо запоминается у контрагента")
    row = db.query(OrdSubmission).filter(OrdSubmission.kind == 'final_contract',
                                         OrdSubmission.local_id == contract.id).one()
    assert row.request.get('clientId') == 'CL-new-payer'


def test_client_id_from_another_contour_is_found_again_not_refused(db, user, monkeypatch):
    """Идентификатор с другого контура — не отказ, а повод найти юрлицо на ЭТОМ (ревью
    24.09.2026): после пробы в песочнице доходный с тем же плательщиком на проде иначе не
    регистрировался вовсе. Чужой идентификатор в колонке при этом не затирается — как у
    колонок договора (`registry.own_contour`)."""
    cp, contract = _setup(db, ord_client_id='CT-prod-1', client_env='prod')
    sent = {}

    def post(path, body):
        if path == '/webapi/v3/clients':
            return 200, {'id': 'CL-demo-payer', 'status': 'Active'}
        sent.update(body)
        return 200, {'id': 'CT-final-99', 'status': 'Created'}
    monkeypatch.setattr(ord_client, 'get', lambda p, params=None: [])
    monkeypatch.setattr(ord_client, 'post', post)

    submit.register_final_contract(db, contract, user)

    db.refresh(cp)
    assert sent.get('clientId') == 'CL-demo-payer'
    assert (cp.ord_client_id, cp.ord_env) == ('CT-prod-1', 'prod'), (
        "демо-прогон затёр боевой идентификатор юрлица")


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


# ── выход из тупика ──────────────────────────────────────────────────────────
#
# Незавершённая попытка блокирует повтор намеренно, но до 30.08.2026 у этого состояния
# не было выхода: сообщение советовало сходить в кабинет ОРД, а записать результат было
# негде. Одна такая попытка провисела в журнале трое суток.

def _stuck(session, contract_id):
    """Попытка, оборвавшаяся без ответа: `finished_at` пуст, повтор закрыт."""
    row = OrdSubmission(kind='final_contract', local_id=contract_id, env='demo',
                        request={}, error='связь оборвалась')
    session.add(row)
    session.commit()
    return row


def test_resolve_without_record_reopens_retry(db, user):
    """«Записи в кабинете нет» — попытка закрыта, повтор разрешён.

    Дубля быть не может: дублировать нечего.
    """
    from app.routers.ord import OrdResolveIn, ord_resolve_submission

    _cp, contract = _setup(db)
    row = _stuck(db, contract.id)
    assert submit.pending(db, 'final_contract', contract.id, 'demo') is not None

    out = ord_resolve_submission(row.id, OrdResolveIn(found=False), db, user)
    assert out["retry_allowed"] is True
    assert submit.pending(db, 'final_contract', contract.id, 'demo') is None, (
        "после отметки «записи нет» повтор обязан открыться — иначе выхода по-прежнему нет"
    )


def test_resolve_with_record_keeps_retry_closed(db, user):
    """«Запись есть» — попытка закрыта, но повтор ОСТАЁТСЯ закрытым.

    Иначе отправка второй раз завела бы в ЕРИР второй объект, а он не отзывается.
    """
    from app.routers.ord import OrdResolveIn, ord_resolve_submission

    _cp, contract = _setup(db)
    row = _stuck(db, contract.id)

    out = ord_resolve_submission(row.id, OrdResolveIn(found=True, ord_id='CT-999'), db, user)
    assert out["retry_allowed"] is False
    db.refresh(row)
    assert row.ord_id == 'CT-999'
    # Повтор закрыт уже не «неизвестностью», а зарегистрированной записью — это проверяет
    # другая ветка (`test_already_registered_contract_is_refused_without_touching_ord`),
    # здесь важно, что сама попытка перестала числиться зависшей.
    assert row.finished_at is not None


def test_resolve_demands_the_identifier_when_record_was_found(db, user):
    """«Нашёл, но какой» — не ответ: без идентификатора запись останется несвязанной."""
    from fastapi import HTTPException

    from app.routers.ord import OrdResolveIn, ord_resolve_submission

    _cp, contract = _setup(db)
    row = _stuck(db, contract.id)
    with pytest.raises(HTTPException) as e:
        ord_resolve_submission(row.id, OrdResolveIn(found=True), db, user)
    assert 'идентификатор' in e.value.detail.lower()


def test_resolved_attempt_cannot_be_resolved_twice(db, user):
    """Закрытая попытка закрыта окончательно: второй след затёр бы первый."""
    from fastapi import HTTPException

    from app.routers.ord import OrdResolveIn, ord_resolve_submission

    _cp, contract = _setup(db)
    row = _stuck(db, contract.id)
    ord_resolve_submission(row.id, OrdResolveIn(found=False), db, user)
    with pytest.raises(HTTPException):
        ord_resolve_submission(row.id, OrdResolveIn(found=False), db, user)


def test_manual_mark_survives_in_the_journal(db, user):
    """След ручного закрытия остаётся навсегда.

    Через год «почему у этой записи не тот путь» — вопрос без ответа, если стереть след.
    """
    from app.routers.ord import OrdResolveIn, ord_resolve_submission

    _cp, contract = _setup(db)
    row = _stuck(db, contract.id)
    ord_resolve_submission(row.id, OrdResolveIn(found=False, note='смотрел вместе с ОРД'),
                           db, user)
    db.refresh(row)
    assert 'связь оборвалась' in row.error, "исходная причина не должна затираться"
    assert 'проверил' in row.error and 'смотрел вместе с ОРД' in row.error


# ── аудит 23.09.2026: 4.L7 и 4.H5 ────────────────────────────────────────────

def test_success_without_an_id_keeps_the_attempt_open(db, user, monkeypatch):
    """4.L7. 200 без идентификатора — не «не создалось», а «не знаем»: запись в ЕРИР
    могла появиться. Закрытая попытка разрешила бы повтор и дубль."""
    cp, contract = _setup(db)
    posts = []

    def _post(path, body):
        posts.append(path)
        return (200, {'status': 'Created'})

    monkeypatch.setattr(ord_client, 'post', _post)
    with pytest.raises(submit.OrdSubmitRefused):
        submit.register_final_contract(db, contract, user)
    row = db.query(OrdSubmission).filter(OrdSubmission.local_id == contract.id).one()
    assert row.finished_at is None, "ответ без id закрыл попытку — повтор разрешён"

    with pytest.raises(submit.OrdSubmitRefused):
        submit.register_final_contract(db, contract, user)
    assert len(posts) == 1


CSET_ID = 999460


@pytest.fixture
def cset(db):
    from types import SimpleNamespace

    def purge():
        db.rollback()
        db.query(OrdSubmission).filter(OrdSubmission.kind == 'creative',
                                       OrdSubmission.local_id == CSET_ID
                                       ).delete(synchronize_session=False)
        db.commit()
    purge()
    yield SimpleNamespace(id=CSET_ID, no=1, erid=None, erid_source='наш',
                          ord_creative_id=None, ord_env=None, ord_status=None,
                          ord_error=None, ord_synced_at=None)
    purge()


def test_creative_registered_without_marker_is_not_registered_again(db, user, cset,
                                                                    monkeypatch):
    """4.H5. ОРД выдал id, а маркер ещё не пришёл. Второе нажатие обязано спрашивать
    статус, а не регистрировать заново: второй креатив в ЕРИР не отозвать."""
    from app.ord import payloads
    monkeypatch.setattr(payloads, 'creative', lambda *a, **kw: {'body': 1})
    posts, gets = [], []
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: posts.append(p) or (200, {'id': 'CR-1', 'status': 'Created'}))
    monkeypatch.setattr(ord_client, 'get',
                        lambda p, params=None: gets.append(p) or {'status': 'Registering'})

    first = submit.issue_marker(db, cset, [], None, None, 'CT-final-1', None, user)
    assert first['erid'] is None and cset.ord_creative_id == 'CR-1'

    second = submit.issue_marker(db, cset, [], None, None, 'CT-final-1', None, user)
    assert len(posts) == 1, "маркер запрошен второй раз — в ЕРИР два креатива"
    assert gets and 'CR-1' in gets[-1], "вместо регистрации должен идти опрос статуса"
    assert second['erid'] is None

    # И прямой вызов регистрации тоже не проходит: правило стоит в самой отправке.
    with pytest.raises(submit.OrdSubmitRefused):
        submit.register_creative(db, cset, [], None, None, 'CT-final-1', None, user)
    assert len(posts) == 1
