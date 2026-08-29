"""Два контура ОРД: демо и прод — разные реестры с разными идентификаторами.

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ ФАЙЛ. До 27.08.2026 идентификатор жил ровно в одной колонке у
записи, то есть модель молча предполагала ОДИН контур. Как только контуров стало два,
это оказалось неверной кардинальностью, и проявилось сразу двумя способами:

  · договор с БОЕВЫМ идентификатором нельзя было завести на демо вовсе — охранник
    повторной регистрации смотрел на заполненность колонки, а не на контур. То есть
    песочница была недоступна ровно для тех записей, ради которых она нужна;
  · если бы охранник пропустил, запись перетёрла бы боевой идентификатор демовским —
    и настоящая связь с ЕРИР потерялась бы ради проверки.

Оба правила теперь в `app/ord/registry.py`, и оба стерегутся здесь: сеть не трогается,
проверяется поведение до и вокруг запроса.
"""
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.ord import client as ord_client
from app.ord import registry
from app.ord import submit as ord_submit
from app.ord.models import OrdSubmission

PROD_ID = 'CT-prod-fixture-1'
DEMO_ID = 'CT-demo-fixture-1'
FAKE_LOCAL_ID = 990001          # номера, которых не бывает у живых строк
FAKE_INN = '9900010000'         # ИНН-пустышка; ключ юрлица в журнале считается из него


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
    """Убрать за собой ОБА ключа.

    У юрлица ключ в журнале — не наш номер строки, а сам ИНН числом, и он другой.
    Не вычистив его, тест оставил бы в живом журнале незакрытую попытку, которая
    навсегда блокирует повтор по этому ключу, — ровно тот мусор, ради которого этот
    файл и появился.
    """
    session.rollback()
    session.query(OrdSubmission).filter(
        OrdSubmission.local_id.in_((FAKE_LOCAL_ID, registry.client_key(FAKE_INN)))
    ).delete(synchronize_session=False)
    session.commit()


def _journal(session, kind, env, ord_id, finished=True):
    from datetime import datetime
    row = OrdSubmission(kind=kind, local_id=FAKE_LOCAL_ID, env=env, request={},
                        started_at=datetime.utcnow(),
                        finished_at=datetime.utcnow() if finished else None,
                        ord_id=ord_id, ord_status='Created')
    session.add(row)
    session.commit()
    return row


# ── чтение: чем запись зовётся на КАЖДОМ контуре ─────────────────────────────
def test_column_answers_only_for_its_own_contour(db):
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'prod',
                             PROD_ID, 'prod') == PROD_ID
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'demo',
                             PROD_ID, 'prod') is None, (
        "боевой идентификатор выдан за демовский — креатив ушёл бы в песочницу "
        "со ссылкой на договор, которого там нет")


def test_column_without_env_counts_as_prod(db):
    """Выгрузка кабинета приехала до колонки `ord_env`, и её записи — боевые."""
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'prod',
                             PROD_ID, None) == PROD_ID
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'demo',
                             PROD_ID, None) is None


def test_journal_answers_for_the_other_contour(db):
    _journal(db, 'final_contract', 'demo', DEMO_ID)
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'demo',
                             PROD_ID, 'prod') == DEMO_ID, (
        "демовская регистрация не нашлась в журнале — второй контур негде хранить")
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'prod',
                             PROD_ID, 'prod') == PROD_ID, "контуры перепутались"


def test_unfinished_attempt_is_not_a_registration(db):
    """Обрыв связи не доказывает ничего — ровно поэтому он блокирует повтор."""
    _journal(db, 'final_contract', 'demo', DEMO_ID, finished=False)
    assert registry.known_id(db, 'final_contract', FAKE_LOCAL_ID, 'demo',
                             None, None) is None


def test_local_placeholder_is_not_an_identifier(db):
    """`local-…` — наша временная метка до заведения в кабинете, а не номер ОРД."""
    assert registry.known_id(db, 'initial_contract', FAKE_LOCAL_ID, 'prod',
                             'local-abc123', 'prod') is None


# ── запись: в колонку только свой контур ─────────────────────────────────────
def test_may_write_column_when_empty_or_same_contour():
    assert registry.own_contour(None, None, 'demo') is True
    assert registry.own_contour('local-abc', None, 'demo') is True
    assert registry.own_contour(PROD_ID, 'prod', 'prod') is True


def test_sandbox_may_not_overwrite_a_live_identifier():
    assert registry.own_contour(PROD_ID, 'prod', 'demo') is False, (
        "демовский идентификатор лёг бы поверх боевого — настоящая связь с ЕРИР "
        "потерялась бы ради проверки в песочнице")
    assert registry.own_contour(PROD_ID, None, 'demo') is False, (
        "запись без контура считается боевой, и песочница её не вытесняет")


def test_live_registration_does_displace_a_sandbox_one():
    """Асимметрия намеренная: в колонке живёт то, по чему сдаётся отчётность.

    Комплект, проверенный на демо, потом регистрируется по-настоящему — и настоящий
    маркер обязан вытеснить пробный, иначе на карточке навсегда останется песочный
    ЕРИД, который нельзя отдать в размещение. Вытесненный не теряется: он в журнале.
    """
    assert registry.own_contour(DEMO_ID, 'demo', 'prod') is True


# ── поведение отправки ───────────────────────────────────────────────────────
def test_prod_registered_contract_is_still_allowed_on_demo(db, monkeypatch):
    """Главное, ради чего всё: боевой договор можно завести в песочнице.

    До сети тест не доходит — отказ или его отсутствие видно раньше.
    """
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    contract = SimpleNamespace(id=FAKE_LOCAL_ID, ord_contract_id=PROD_ID,
                               ord_env='prod', counterparty_id=None)

    with pytest.raises(ord_submit.OrdSubmitRefused) as e:
        ord_submit.register_final_contract(db, contract, None)
    assert 'не указан контрагент' in str(e.value), (
        "отказ пришёл раньше, чем дошло до контрагента, — значит охранник опять "
        f"смотрит на колонку, а не на контур: {e.value}")


def test_same_contour_registration_is_refused_as_before(db, monkeypatch):
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    contract = SimpleNamespace(id=FAKE_LOCAL_ID, ord_contract_id=DEMO_ID,
                               ord_env='demo', counterparty_id=None)

    with pytest.raises(ord_submit.OrdSubmitRefused) as e:
        ord_submit.register_final_contract(db, contract, None)
    assert 'уже зарегистрирован на контуре demo' in str(e.value)


def test_creative_marked_on_prod_may_still_be_issued_on_demo(db, monkeypatch):
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до сети доходить не должно'))
    cset = SimpleNamespace(id=FAKE_LOCAL_ID, erid='ERID-prod-1', ord_creative_id='CR-1',
                           ord_env='prod', erid_source='наш')

    # Дальше сборки тела дойти не должно — там не хватает полей у заглушки, и это
    # нормально: проверяется ровно то, что охранник маркера ПРОПУСТИЛ, а не то, что
    # запрос собрался. Ловим любое исключение и смотрим, чем именно отказали.
    try:
        ord_submit.register_creative(db, cset, [], None, None, None, None, None)
    except ord_submit.OrdSubmitRefused as e:
        assert 'уже есть маркер' not in str(e), (
            f"боевой маркер запретил выпуск в песочнице: {e}")
    except Exception:
        pass          # упало на сборке тела — значит охранник пропустил


def test_creative_marked_on_this_contour_is_refused(db, monkeypatch):
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до сети доходить не должно'))
    cset = SimpleNamespace(id=FAKE_LOCAL_ID, erid='ERID-demo-1', ord_creative_id='CR-2',
                           ord_env='demo', erid_source='наш')

    with pytest.raises(ord_submit.OrdSubmitRefused) as e:
        ord_submit.register_creative(db, cset, [], None, None, None, None, None)
    assert 'уже есть маркер' in str(e.value)


# ── ключ юрлица ──────────────────────────────────────────────────────────────
def test_client_key_is_the_same_here_and_in_submit():
    """У юрлица нет нашей строки, и ключом служит сам ИНН — в ОДНОМ месте.

    ИНН синтетический. Реальный здесь был бы данными клиента в коде: 7700000123 ведёт
    себя ровно так же, а имя компании из репозитория не вычитывается.
    """
    assert registry.client_key('7700000123') == 770000012
    assert registry.client_key('77 00 00 01 23') == 770000012, "разделители не убраны"
    assert registry.client_key('') == 0


def test_contract_and_counterparty_models_still_carry_the_env_column():
    """Колонка контура — опора всей развязки; её пропажа обязана падать тестом."""
    assert hasattr(Contract, 'ord_env')
    assert hasattr(Counterparty, 'ord_env')


# ── чем подписана незавершённая попытка ──────────────────────────────────────
def test_a_break_says_whether_it_was_the_network_or_us():
    """Найдено 27.08.2026: `TypeError` нашего кода лежал в журнале как «связь оборвалась».

    Блокировка повтора одинаковая в обоих случаях — запрос мог уйти и создать запись
    в ЕРИР, — но человек, который пойдёт сверяться с кабинетом, по этой подписи решает,
    искать сеть или чинить нас.
    """
    import httpx

    network = ord_submit._break_label(httpx.ConnectTimeout('таймаут'))
    assert network.startswith('связь оборвалась'), network

    ours = ord_submit._break_label(TypeError('cannot unpack non-iterable NoneType'))
    assert 'связь' not in ours, f"ошибка нашего кода снова подписана как сетевая: {ours}"
    assert 'TypeError' in ours, "тип ошибки обязан остаться в тексте — по нему и ищут"


def test_our_own_failure_still_blocks_the_retry(db, monkeypatch):
    """Подпись изменилась, осторожность — нет: неизвестность та же.

    Строка остаётся незакрытой (`finished_at IS NULL`), и следующая попытка по этой же
    записи отклоняется, пока человек не посмотрит в кабинет.
    """
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')

    def boom(path, body):
        raise TypeError('cannot unpack non-iterable NoneType object')
    monkeypatch.setattr(ord_client, 'post', boom)
    monkeypatch.setattr(ord_client, 'get', lambda p, params=None: [])

    with pytest.raises(TypeError):
        ord_submit.ensure_client(db, FAKE_INN, 'Пустышка', None)

    stuck = ord_submit.pending(db, 'client', registry.client_key(FAKE_INN), 'demo')
    assert stuck is not None, "попытка закрылась — повтор разрешён там, где исход неизвестен"
    assert 'на нашей стороне' in (stuck.error or ''), stuck.error

