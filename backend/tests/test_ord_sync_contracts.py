"""Строки из API и строки из выгрузки — одной формы, и обе идут к одному писателю.

ЗАЧЕМ ЭТОТ ТЕСТ. У зеркала ОРД появился второй источник: раньше только файл выгрузки,
теперь ещё и `GET /contracts/*`. Писатель общий (`importer.upsert_rows`), и держится это
исключительно на том, что обе стороны строят словарь с одинаковыми ключами. Разъедутся —
писатель молча получит `None` там, где ждал значение, и зеркало наполнится дырами,
которые заметят на сдаче отчётности.

Ответы ОРД здесь не сочинены: каждый сперва валидируется на ОФИЦИАЛЬНОЙ схеме из
фикстуры спеки. Иначе тест сверял бы код с моими представлениями об API, а не с API.
"""
import io
import json
import os
from datetime import date

import pytest

from app.ord import importer, sync

SPEC = os.path.join(os.path.dirname(__file__), 'fixtures', 'mediascout_v3_schemas.json')


@pytest.fixture(scope='module')
def schemas():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)['components']['schemas']


def valid(schemas, name, body):
    """Ответ ОРД против официальной схемы: лишних полей нет, перечисления свои."""
    props = schemas[name]['properties']
    unknown = [k for k in body if k not in props]
    assert not unknown, f"{name}: полей {unknown} в официальной схеме нет"
    for key, value in body.items():
        allowed = props[key].get('enum')
        if allowed is not None:
            assert value in allowed, f"{name}.{key}: {value!r} не из {allowed}"
    return body


# ── формы строк ──────────────────────────────────────────────────────────────
class _NoClients:
    """Резолвер-заглушка: проверяем форму, а не поход в ОРД."""

    def get(self, _):
        return ('7700000001', 'ООО «Заказчик»')


def test_api_final_row_has_same_keys_as_file_row(schemas):
    """Ключи строки доходного из API совпадают с тем, что даёт разбор выгрузки.

    Эталон берётся не из головы, а из самого `parse_final`: список полей, которые
    писатель раскладывает по колонкам, живёт там.
    """
    item = valid(schemas, 'FinalContractResponse', {
        'id': 'CT-final-1', 'cid': None, 'number': 'ПМ-01/2026',
        'date': '2026-01-15T00:00:00', 'expirationDate': None,
        'type': 'ServiceAgreement', 'status': 'Active',
        'clientId': 'CT-client-1', 'isAgentActingForPublisher': False,
        'erirValidationError': None,
    })
    row = sync._final_row(item, _NoClients())

    expected = {'ord_id', 'ord_cid', 'number', 'date', 'expiration_date', 'type',
                'client_inn', 'client_name', 'parent_number',
                'is_agent_acting_for_publisher', 'status', 'status_at',
                'error_text', 'warnings'}
    assert set(row) == expected, "форма строки разошлась с разбором выгрузки"
    assert row['date'] == date(2026, 1, 15), "дата обязана стать date, а не остаться строкой"
    assert row['client_inn'] == '7700000001', "ИНН стороны обязан быть разрешён"


def test_api_initial_row_has_same_keys_as_file_row(schemas):
    item = valid(schemas, 'InitialContractResponse', {
        'id': 'CT-init-1', 'cid': None, 'number': 'ТД-7',
        'date': '2025-03-01T00:00:00', 'expirationDate': None, 'amount': 100.0,
        'type': 'MediationContract', 'subjectType': 'Mediation',
        'actionType': 'Contracting', 'status': 'Active',
        'isAgentActingForPublisher': True,
        'clientInn': '7700000002', 'clientName': 'ООО «Рекламодатель»',
        'contractorInn': '7700000003', 'contractorName': 'ООО «Исполнитель»',
        'finalContractId': 'CT-final-1', 'erirValidationError': None,
    })
    row = sync._initial_row(item)

    expected = {'ord_id', 'ord_cid', 'number', 'date', 'expiration_date', 'amount',
                'type', 'subject_type', 'action_type', 'is_agent_acting_for_publisher',
                'client_inn', 'client_name', 'contractor_inn', 'contractor_name',
                'final_ord_id', 'status', 'status_at', 'error_text', 'warnings'}
    assert set(row) == expected, "форма строки разошлась с разбором выгрузки"
    assert row['final_ord_id'] == 'CT-final-1', (
        "связь с доходным обязана ехать: без неё изначальный повиснет без цепочки")


def test_outer_row_takes_contractor_not_client(schemas):
    """У расходного договора наша сторона — исполнитель (площадка), а не заказчик.

    Перепутать легко: форма строки та же, что у доходного, и подменяется одно поле.
    Ошибка была бы тихой — договор разметился бы на чужого контрагента.
    """
    seen = []

    class _Spy:
        def get(self, ord_id):
            seen.append(ord_id)
            return ('7700000009', 'ООО «Площадка»')

    item = valid(schemas, 'OuterContractResponse', {
        'id': 'CT-outer-1', 'cid': None, 'number': 'РС-3',
        'date': '2025-05-05T00:00:00', 'type': 'ServiceAgreement',
        'status': 'Active', 'contractorId': 'CT-contractor-9',
        'isAgentActingForPublisher': False, 'erirValidationError': None,
    })
    row = sync._outer_row(item, _Spy())

    assert row['client_inn'] == '7700000009'
    assert 'CT-contractor-9' in seen, "сторона расходного берётся по contractorId"


# ── единственность писателя ──────────────────────────────────────────────────
def test_mirror_has_exactly_one_writer():
    """Писатель зеркала один, а читателей два.

    Пин на то, что синк по API не завёл собственную запись: у писателя внутри порядок
    разметки, сведение латиницы в номерах и создание связей — в двух копиях они
    разошлись бы молча.
    """
    import inspect
    source = inspect.getsource(sync)
    assert 'importer.upsert_rows' in source, "синк обязан писать через общего писателя"
    for forbidden in ('db.add(OrdInitialContract', 'db.add(OrdInitialFinalLink'):
        assert forbidden not in source, (
            f"синк пишет зеркало сам ({forbidden}) — писатель должен остаться один")
    assert hasattr(importer, 'upsert_rows') and hasattr(importer, 'upsert'), (
        "upsert по файлам обязан остаться: выгрузка — по-прежнему рабочий путь, "
        "пока доступа к API нет")
