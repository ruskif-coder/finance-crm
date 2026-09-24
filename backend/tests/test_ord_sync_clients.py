"""Фаза 1: проставление `ord_client_id` по ИНН — проверяется без доступа к ОРД.

Поддельные ответы не выдуманы: каждый сперва валидируется на ОФИЦИАЛЬНОЙ схеме
`ClientResponse` из фикстуры спеки, и только потом скармливается синку. Иначе тест
проверял бы согласие кода с моими представлениями об API, а не с API — ровно так и
появилась прошлая ошибка, когда разбор по стороннему клиенту два дня считался верным.

Правило синка, которое здесь закреплено: сопоставляем ТОЛЬКО по ИНН и ТОЛЬКО когда
нашлось ровно одно юрлицо. Ноль и несколько — в отчёт, а не в подстановку: неверный
`clientId` уедет в ЕРИР внутри договора и не отзовётся.
"""
import io
import json
import os
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import Counterparty
from app.ord import client as ord_client
from app.ord import sync

SPEC = os.path.join(os.path.dirname(__file__), 'fixtures', 'mediascout_v3_schemas.json')
TEST_INNS = ('7700000071', '7700000072', '7700000073', '7700000074',
             '7700000075', '7700000076', '7700000077', '7700000078',
             '7700000079')
PREFIX = 'CTsync'


@pytest.fixture(scope='module')
def schemas():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)['components']['schemas']


@pytest.fixture
def db():
    session = SessionLocal()
    clash = session.query(Counterparty.inn).filter(Counterparty.inn.in_(TEST_INNS)).all()
    assert not clash, f"фиктивные ИНН {TEST_INNS} заняты реальными контрагентами {clash}"
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _purge(session):
    session.rollback()
    session.query(Counterparty).filter(Counterparty.inn.in_(TEST_INNS)
                                       ).delete(synchronize_session=False)
    session.commit()


def _make(session, inn, name):
    cp = Counterparty(name=f'{PREFIX} {name}', inn=inn, status='действующий')
    session.add(cp)
    session.flush()
    return cp


def ord_client_response(schemas, ord_id, inn):
    """Ответ ОРД про юрлицо — сверенный со схемой, а не сочинённый."""
    body = {'id': ord_id, 'inn': inn, 'name': 'ООО «Тест»',
            'legalForm': 'JuridicalPerson', 'isPhysicalPersonAddressExists': False,
            'status': 'Active'}
    props = schemas['ClientResponse']['properties']
    unknown = [k for k in body if k not in props]
    assert not unknown, f"ClientResponse: полей {unknown} в официальной схеме нет"
    for key, value in body.items():
        allowed = props[key].get('enum')
        if allowed is not None:
            assert value in allowed, f"ClientResponse.{key}: {value!r} не из {allowed}"
    return body


@pytest.fixture
def fake_ord(monkeypatch, schemas):
    """Подменяет транспорт. Ключ ответа — ИНН из параметров запроса."""
    answers = {}

    def _get(path, params=None):
        assert path == '/webapi/v3/clients', f'неожиданный путь {path}'
        return answers.get((params or {}).get('Inn'), [])

    monkeypatch.setattr(ord_client, 'get', _get)
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    return SimpleNamespace(answers=answers, respond=ord_client_response, schemas=schemas)


def test_single_match_by_inn_is_taken(db, fake_ord):
    cp = _make(db, TEST_INNS[0], 'Один')
    fake_ord.answers[TEST_INNS[0]] = [fake_ord.respond(fake_ord.schemas, 'CT-ord-1', TEST_INNS[0])]

    report = sync.sync_clients(db)

    db.refresh(cp)
    assert cp.ord_client_id == 'CT-ord-1'
    assert cp.ord_env == 'demo', "контур обязан ехать вместе с идентификатором"
    assert cp.ord_synced_at is not None
    assert report['matched'] >= 1


def test_several_matches_are_reported_not_guessed(db, fake_ord):
    """Два юрлица на один ИНН — не подставляем ничего.

    Случай не теоретический: «OKKAM» в ОРД это три разных юрлица, и выбор наугад
    уехал бы в ЕРИР внутри договора.
    """
    cp = _make(db, TEST_INNS[1], 'Двойник')
    fake_ord.answers[TEST_INNS[1]] = [
        fake_ord.respond(fake_ord.schemas, 'CT-ord-a', TEST_INNS[1]),
        fake_ord.respond(fake_ord.schemas, 'CT-ord-b', TEST_INNS[1]),
    ]

    report = sync.sync_clients(db)

    db.refresh(cp)
    assert cp.ord_client_id is None, "при неоднозначности подставлять нельзя"
    assert any(r['inn'] == TEST_INNS[1] for r in report['ambiguous'])


def test_client_record_wins_over_the_agent_one(db, fake_ord):
    """Одно юрлицо в ОРД бывает в двух ролях: `CL…` — клиент (заказчик), `AG…` — агент
    (исполнитель). Замер на боевом контуре 24.09.2026: все 52 доходных договора ссылаются
    на заказчика `CL…`, исполнитель у них — `AG…`. Агентство, которое бывает и тем и
    другим, отдаёт по ИНН две записи — и 34 ИНН из 170 уходили в «неоднозначные».
    Для `clientId` нужна клиентская запись: ровно одна `CL` среди найденных — берём её."""
    cp = _make(db, TEST_INNS[7], 'Агентство в двух ролях')
    fake_ord.answers[TEST_INNS[7]] = [
        fake_ord.respond(fake_ord.schemas, 'AGrole-agent', TEST_INNS[7]),
        fake_ord.respond(fake_ord.schemas, 'CLrole-client', TEST_INNS[7]),
    ]
    sync.sync_clients(db)
    db.refresh(cp)
    assert cp.ord_client_id == 'CLrole-client'


def test_two_client_records_stay_ambiguous(db, fake_ord):
    """Две клиентские записи на ИНН — это уже настоящая неоднозначность, не угадываем."""
    cp = _make(db, TEST_INNS[8], 'Два клиента')
    fake_ord.answers[TEST_INNS[8]] = [
        fake_ord.respond(fake_ord.schemas, 'CLtwin-a', TEST_INNS[8]),
        fake_ord.respond(fake_ord.schemas, 'CLtwin-b', TEST_INNS[8]),
        fake_ord.respond(fake_ord.schemas, 'AGtwin-c', TEST_INNS[8]),
    ]
    report = sync.sync_clients(db)
    db.refresh(cp)
    assert cp.ord_client_id is None
    assert any(r['inn'] == TEST_INNS[8] for r in report['ambiguous'])


def test_absent_in_ord_is_work_list_not_error(db, fake_ord):
    """Юрлица нет в кабинете — это список работы, а не список ошибок."""
    cp = _make(db, TEST_INNS[2], 'Отсутствует')
    fake_ord.answers[TEST_INNS[2]] = []

    report = sync.sync_clients(db)

    db.refresh(cp)
    assert cp.ord_client_id is None
    assert any(r['inn'] == TEST_INNS[2] for r in report['not_in_ord'])
    assert not report['failed'], "отсутствие в ОРД не должно попадать в ошибки"


def test_refusal_of_one_client_does_not_stop_the_rest(db, fake_ord):
    """Отказ ОРД по одному контрагенту не роняет прогон.

    Иначе один битый ИНН останавливал бы сверку двухсот, и запускать её пришлось бы
    столько раз, сколько в справочнике проблемных строк.
    """
    bad = _make(db, TEST_INNS[3], 'Отказной')
    good = _make(db, TEST_INNS[0], 'Нормальный')
    fake_ord.answers[TEST_INNS[0]] = [fake_ord.respond(fake_ord.schemas, 'CT-ord-ok', TEST_INNS[0])]

    def _get(path, params=None):
        inn = (params or {}).get('Inn')
        if inn == TEST_INNS[3]:
            raise ord_client.OrdError(400, 'ОРД отклонил запрос — Inn: некорректный ИНН')
        return fake_ord.answers.get(inn, [])

    import app.ord.sync as sync_module
    sync_module.client.get = _get

    report = sync.sync_clients(db)

    db.refresh(good)
    db.refresh(bad)
    assert good.ord_client_id == 'CT-ord-ok', "исправный контрагент должен быть обработан"
    assert bad.ord_client_id is None
    assert any('некорректный ИНН' in f['why'] for f in report['failed'])


def test_demo_run_never_touches_a_production_id(db, fake_ord):
    """4.M3 аудита 23.09.2026. Сверка на демо брала в работу и боевые строки (и строки с
    пустым контуром — они боевые по умолчанию) и либо писала поверх демо-id, либо
    стирала боевой. «Песочница боевой не вытесняет никогда» — правило
    `registry.own_contour`, и сверка обязана держать его так же, как отправка."""
    prod = _make(db, TEST_INNS[4], 'Боевой')
    prod.ord_client_id, prod.ord_env = 'CT-prod-1', 'prod'
    legacy = _make(db, TEST_INNS[5], 'Без контура')
    legacy.ord_client_id, legacy.ord_env = 'CT-prod-2', None
    gone = _make(db, TEST_INNS[6], 'Нет на демо')
    gone.ord_client_id, gone.ord_env = 'CT-prod-3', 'prod'
    db.commit()
    fake_ord.answers[TEST_INNS[4]] = [fake_ord.respond(fake_ord.schemas, 'CT-demo-1', TEST_INNS[4])]
    fake_ord.answers[TEST_INNS[5]] = [fake_ord.respond(fake_ord.schemas, 'CT-demo-2', TEST_INNS[5])]

    sync.sync_clients(db)

    for cp, want in ((prod, 'CT-prod-1'), (legacy, 'CT-prod-2'), (gone, 'CT-prod-3')):
        db.refresh(cp)
        assert cp.ord_client_id == want, f"{cp.name}: демо-сверка переписала боевой id"


def test_prod_run_still_replaces_a_demo_id(db, fake_ord, monkeypatch):
    """Обратное направление обязано остаться: боевой вытесняет песочницу."""
    cp = _make(db, TEST_INNS[7], 'С демо')
    cp.ord_client_id, cp.ord_env = 'CT-demo-3', 'demo'
    db.commit()
    monkeypatch.setattr(ord_client, 'env', lambda: 'prod')
    fake_ord.answers[TEST_INNS[7]] = [fake_ord.respond(fake_ord.schemas, 'CT-prod-4', TEST_INNS[7])]

    sync.sync_clients(db)

    db.refresh(cp)
    assert (cp.ord_client_id, cp.ord_env) == ('CT-prod-4', 'prod')


def test_prod_run_keeps_a_legacy_prod_id_it_could_not_confirm(db, fake_ord, monkeypatch):
    """Ревью 23.09.2026. Пустой контур — боевой (`ENV_WHEN_UNKNOWN`), а ветка «снять
    чужой» сравнивала его с пустой строкой: прогон на проде стирал настоящий боевой id,
    стоило ОРД один раз не найти юрлицо."""
    cp = _make(db, TEST_INNS[8], 'Боевой из выгрузки')
    cp.ord_client_id, cp.ord_env = 'CT-prod-5', None
    db.commit()
    monkeypatch.setattr(ord_client, 'env', lambda: 'prod')
    fake_ord.answers[TEST_INNS[8]] = []

    report = sync.sync_clients(db)

    db.refresh(cp)
    assert cp.ord_client_id == 'CT-prod-5', "боевой id стёрт прогоном по проду"
    assert not report['cleared']
