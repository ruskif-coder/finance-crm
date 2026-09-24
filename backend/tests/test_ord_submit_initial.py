"""Фаза 3: изначальный договор и обе его стороны.

Три вещи, которые здесь закреплены, — не про удобство, а про необратимость:

  · **юрлицо ищется ПЕРЕД заведением.** `POST /clients` на существующий ИНН в лучшем
    случае откажет, в худшем заведёт двойника, а разбирать двойников юрлиц в ЕРИР
    некому. Найдено несколько — отказ, выбирать наугад нельзя;
  · **местная заглушка `local-<hex>` заменяется настоящим идентификатором**, а `origin`
    перестаёт быть `manual`. Ради этого заглушка и вводилась: строка не теряет связей
    со сделкой, а следующая загрузка выгрузки не считает договор своим и не затирает;
  · **`attachexisting` — второй конец M:N.** 22 из 24 повторяющихся изначальных
    договоров в выгрузке привязаны к РАЗНЫМ доходным; без этой операции такую цепочку
    в ОРД не собрать.

Транспорт подменён, до настоящего ОРД ни один тест не доходит.
"""
from datetime import date

import pytest

from app.database import SessionLocal
from app.ord import client as ord_client
from app.ord import submit
from app.ord.models import OrdInitialContract, OrdInitialFinalLink, OrdSubmission

PREFIX = 'CTinit'
ADV_INN = '7700000091'
EXE_INN = '7700000092'


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _purge(session):
    session.rollback()
    ids = [r.id for r in session.query(OrdInitialContract)
           .filter(OrdInitialContract.number.like(f'{PREFIX}%')).all()]
    if ids:
        session.query(OrdInitialFinalLink).filter(
            OrdInitialFinalLink.initial_contract_id.in_(ids)).delete(synchronize_session=False)
        session.query(OrdSubmission).filter(
            OrdSubmission.local_id.in_(ids)).delete(synchronize_session=False)
        session.query(OrdInitialContract).filter(
            OrdInitialContract.id.in_(ids)).delete(synchronize_session=False)
    session.query(OrdSubmission).filter(
        OrdSubmission.kind == 'client',
        OrdSubmission.local_id.in_([int(ADV_INN[:9]), int(EXE_INN[:9])])
    ).delete(synchronize_session=False)
    session.commit()


def _initial(session, ord_id=None):
    row = OrdInitialContract(
        ord_id=ord_id or ('local-' + PREFIX + 'aaa'), origin='manual',
        number=f'{PREFIX}-1', date=date(2025, 3, 1), type='MediationContract',
        subject_type='Mediation', action_type='Contracting',
        advertiser_inn=ADV_INN, advertiser_name='CTtest Рекламодатель',
        contractor_inn=EXE_INN, contractor_name='CTtest Исполнитель')
    session.add(row)
    session.flush()
    session.commit()
    return row


@pytest.fixture
def user(db):
    from app.models import User
    return db.query(User).first()


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.delenv('ORD_ALLOW_PROD_WRITE', raising=False)


def test_existing_client_is_found_not_created(db, user, monkeypatch):
    """Юрлицо уже в ОРД — заводить второе нельзя."""
    posted = []
    monkeypatch.setattr(ord_client, 'get',
                        lambda p, params=None: [{'id': 'CT-cli-1', 'inn': ADV_INN}])
    monkeypatch.setattr(ord_client, 'post', lambda p, b: posted.append(p))

    got = submit.ensure_client(db, ADV_INN, 'CTtest Рекламодатель', user)

    assert got == 'CT-cli-1'
    assert not posted, "существующее юрлицо не должно заводиться повторно"


def test_several_clients_on_one_inn_are_refused(db, user, monkeypatch):
    """«OKKAM» в ОРД — три юрлица. Выбор наугад уехал бы в договор и в ЕРИР."""
    monkeypatch.setattr(ord_client, 'get', lambda p, params=None: [
        {'id': 'CT-a', 'inn': ADV_INN}, {'id': 'CT-b', 'inn': ADV_INN}])
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до отправки доходить не должно'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.ensure_client(db, ADV_INN, 'CTtest', user)
    assert 'несколько юрлиц' in str(e.value)


def test_absent_client_is_created_and_logged(db, user, monkeypatch):
    monkeypatch.setattr(ord_client, 'get', lambda p, params=None: [])
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: (200, {'id': 'CT-new-1', 'status': 'Active'}))

    got = submit.ensure_client(db, ADV_INN, 'CTtest Рекламодатель', user)

    assert got == 'CT-new-1'
    row = (db.query(OrdSubmission)
             .filter(OrdSubmission.kind == 'client',
                     OrdSubmission.local_id == int(ADV_INN[:9])).one())
    assert row.finished_at is not None and row.ord_id == 'CT-new-1'
    assert row.request['inn'] == ADV_INN, "тело обязано сохраниться"


def test_registration_replaces_local_stub_and_creates_link(db, user, monkeypatch):
    """Заглушка уступает место настоящему id, origin становится 'ord', связь заводится."""
    initial = _initial(db)
    monkeypatch.setattr(ord_client, 'get',
                        lambda p, params=None: [{'id': 'CT-cli-' + (params or {}).get('Inn', ''),
                                                 'inn': (params or {}).get('Inn')}])
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: (200, {'id': 'CT-init-99', 'status': 'Created'}))

    result = submit.register_initial_contract(db, initial, 'CT-final-1', user)

    db.refresh(initial)
    assert result['ord_id'] == 'CT-init-99'
    assert initial.ord_id == 'CT-init-99', "заглушка обязана быть заменена"
    assert initial.origin == 'ord', "договор теперь в кабинете, а не заведён у нас"
    assert initial.ord_env == 'demo'
    link = (db.query(OrdInitialFinalLink)
              .filter(OrdInitialFinalLink.initial_contract_id == initial.id).one())
    assert link.final_ord_id == 'CT-final-1'


def test_registration_without_final_is_refused(db, user, monkeypatch):
    """`finalContractId` обязателен: изначальный создаётся только прикреплённым."""
    initial = _initial(db)
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до отправки доходить не должно'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_initial_contract(db, initial, '', user)
    assert 'прикреплённым к доходному' in str(e.value)


def test_already_registered_initial_is_refused(db, user, monkeypatch):
    """Повтор запрещён НА ТОМ ЖЕ контуре — с 27.08.2026 проверка контурная.

    Раньше смотрели на заполненность колонки, и договор с боевым идентификатором
    нельзя было завести в песочнице вовсе. Теперь контур указывается явно, и правило
    звучит так: там, где уже зарегистрирован, — отказ; на другом контуре — можно.
    """
    initial = _initial(db, ord_id='CT-real-1')
    initial.origin = 'ord'
    initial.ord_env = 'demo'
    db.commit()
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до отправки доходить не должно'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_initial_contract(db, initial, 'CT-final-1', user)
    assert 'уже в ОРД на контуре demo' in str(e.value)


def test_initial_registered_on_prod_may_be_registered_on_demo(db, user, monkeypatch):
    """То, ради чего развязка и делалась: боевой договор заводится в песочнице.

    Дальше отказа по юрлицу не идём — важно, что отказ НЕ про «уже в ОРД».
    """
    initial = _initial(db, ord_id='CT-real-2')
    initial.origin = 'ord'
    initial.ord_env = 'prod'
    initial.advertiser_inn = None
    db.commit()
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до отправки доходить не должно'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.register_initial_contract(db, initial, 'CT-final-1', user)
    assert 'уже в ОРД' not in str(e.value), (
        f"боевая регистрация закрыла дорогу в песочницу: {e.value}")


def test_attach_adds_second_final_to_the_same_initial(db, user, monkeypatch):
    """Второй конец M:N: один изначальный под двумя разными доходными."""
    initial = _initial(db, ord_id='CT-real-2')
    initial.origin = 'ord'
    initial.ord_env = 'demo'
    db.add(OrdInitialFinalLink(initial_contract_id=initial.id, final_ord_id='CT-final-1'))
    db.commit()
    monkeypatch.setattr(ord_client, 'post', lambda p, b: (200, {'id': 'CT-real-2'}))

    submit.attach_initial(db, initial, 'CT-final-2', user)

    links = {l.final_ord_id for l in db.query(OrdInitialFinalLink)
             .filter(OrdInitialFinalLink.initial_contract_id == initial.id).all()}
    assert links == {'CT-final-1', 'CT-final-2'}


def test_attach_of_unregistered_initial_is_refused(db, user, monkeypatch):
    """Прикреплять нечего, пока договора нет в кабинете."""
    initial = _initial(db)
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до отправки доходить не должно'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.attach_initial(db, initial, 'CT-final-2', user)
    assert 'сначала регистрация' in str(e.value)


def test_duplicate_attach_is_refused(db, user, monkeypatch):
    initial = _initial(db, ord_id='CT-real-3')
    initial.origin = 'ord'
    initial.ord_env = 'demo'
    db.add(OrdInitialFinalLink(initial_contract_id=initial.id, final_ord_id='CT-final-1'))
    db.commit()
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до отправки доходить не должно'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.attach_initial(db, initial, 'CT-final-1', user)
    assert 'уже есть' in str(e.value)


# ── аудит 23.09.2026, 4.M4: контур при регистрации изначального ─────────────

def test_attach_never_sends_an_id_from_another_contour(db, user, monkeypatch):
    """На проде все изначальные договоры — демовские. Прикрепление с демо-id ушло бы в
    боевой ЕРИР ссылкой на чужую запись; вместо этого — отказ до сети."""
    initial = _initial(db, ord_id='CT-demo-9')
    initial.origin = 'ord'
    initial.ord_env = 'demo'
    db.commit()
    monkeypatch.setattr(ord_client, 'env', lambda: 'prod')
    monkeypatch.setenv('ORD_ALLOW_PROD_WRITE', '1')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail(f'на прод ушло {b}'))

    with pytest.raises(submit.OrdSubmitRefused) as e:
        submit.attach_initial(db, initial, 'CT-final-prod', user)
    assert 'prod' in str(e.value)


def test_register_route_uses_ids_of_the_contour_it_sends_to(db, user, monkeypatch):
    """Ручка брала доходный прямо из колонки и выбирала ветку по колонке изначального.
    На проде при демовских колонках обе ветки отправили бы демо-id в боевой ЕРИР."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.routers import ord as ord_router

    initial = _initial(db, ord_id='CT-demo-10')
    initial.origin = 'ord'
    initial.ord_env = 'demo'
    db.commit()
    deal = SimpleNamespace(id=999470, ord_initial_contract_id=initial.id)
    final = SimpleNamespace(id=999471, ord_contract_id='CT-demo-final', ord_env='demo')
    monkeypatch.setattr(ord_router, '_deal_or_404', lambda db, u, i: deal)
    monkeypatch.setattr(ord_router, 'resolve_final',
                        lambda db, d: SimpleNamespace(contract=final,
                                                      final_ord_id='CT-demo-final'))
    monkeypatch.setattr(ord_client, 'is_configured', lambda: True)
    monkeypatch.setattr(ord_client, 'env', lambda: 'prod')
    monkeypatch.setenv('ORD_ALLOW_PROD_WRITE', '1')
    sent = []
    monkeypatch.setattr(ord_client, 'post', lambda p, b: sent.append(b) or (200, {'id': 'X'}))
    monkeypatch.setattr(ord_client, 'get', lambda p, params=None: [{'id': 'CT-cli'}])

    with pytest.raises(HTTPException) as e:
        ord_router.ord_register_initial(deal.id, ord_router.RegisterInitial(), db, user)
    assert e.value.status_code == 400
    assert not sent, f"в боевой ОРД ушли демо-идентификаторы: {sent}"
