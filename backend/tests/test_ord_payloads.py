"""Наши тела запросов в ОРД проверяются на ОФИЦИАЛЬНЫХ схемах — без доступа к API.

Фикстура `fixtures/mediascout_v3_schemas.json` — 95 схем из `swagger/v3/swagger.json`
демо-контура (версия API 3.2, скачано 26.08.2026). Доступа к ОРД ещё нет, но проверять
отправку можно уже сейчас: недостающее обязательное поле, чужое значение перечисления
и лишний ключ видны прямо из схемы.

ЗАЧЕМ ИМЕННО ТАК. Разбор API, сделанный по стороннему клиенту, врал дважды: сумма акта
там была одним полем вместо четырёх, а тип `VirtualFinalContract`, которого в настоящей
спеке нет вовсе, попал в наши перечисления как «API его принимает». Обе ошибки прожили
двое суток и были найдены глазами при сверке. Этот тест находит такое механически.

Проверка написана руками, а не через `jsonschema`: библиотеки в контейнере нет, а
заводить зависимость ради трёх правил (обязательные, перечисления, лишние ключи) —
дороже, чем эти три правила написать. Ровно они и ловят наши отказы.
"""
import io
import json
import os
from datetime import date
from types import SimpleNamespace

import pytest

from app.ord.payloads import (OrdPayloadError, client, final_contract,
                              initial_contract, legal_form)

SPEC = os.path.join(os.path.dirname(__file__), 'fixtures', 'mediascout_v3_schemas.json')


@pytest.fixture(scope='module')
def schemas():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)['components']['schemas']


def check(schemas, name, body):
    """Тело против схемы: обязательные на месте, перечисления свои, лишнего нет."""
    schema = schemas[name]
    props = schema.get('properties', {})

    missing = [f for f in schema.get('required', []) if f not in body]
    assert not missing, f"{name}: не хватает обязательных полей {missing}"

    unknown = [k for k in body if k not in props]
    assert not unknown, (
        f"{name}: поля {unknown} в схеме отсутствуют — опечатка или поле из другой "
        f"версии API")

    for key, value in body.items():
        allowed = props[key].get('enum')
        if allowed is not None:
            assert value in allowed, (
                f"{name}.{key}: значение {value!r} не из перечисления {allowed}")


# ── форма юрлица ─────────────────────────────────────────────────────────────
def test_legal_form_of_company_is_derived_from_inn_length():
    assert legal_form('7700000000') == 'JuridicalPerson'


def test_twelve_digit_inn_is_refused_instead_of_guessed():
    """Двенадцать цифр — ИП или физлицо, и различить их по ИНН нельзя.

    Отказ, а не «наверное, ИП»: неверная форма стороны уезжает в ЕРИР и не отзывается.
    Таких контрагентов у нас 27 из 211 — случай не экзотический.
    """
    with pytest.raises(OrdPayloadError) as e:
        legal_form('770000000000')
    assert 'ИП или физлицо' in str(e.value)


# ── тела запросов ────────────────────────────────────────────────────────────
def test_client_payload_matches_official_schema(schemas):
    cp = SimpleNamespace(name='ООО «Тест»', inn='7700000000')
    check(schemas, 'CreateClientRequest', client(cp))


def test_final_contract_payload_matches_official_schema(schemas):
    contract = SimpleNamespace(id=1, contract_number='ПМ-01/2026',
                               contract_date=date(2026, 1, 15))
    body = final_contract(contract, client_ord_id='CTclient123')
    check(schemas, 'CreateFinalContractRequest', body)
    assert body['type'] == 'ServiceAgreement', "доходный договор всегда услуговый"


def test_initial_contract_payload_matches_official_schema(schemas):
    initial = SimpleNamespace(id=2, number='ТД-7', date=date(2025, 3, 1),
                              type='MediationContract', subject_type='Mediation',
                              action_type='Contracting')
    body = initial_contract(initial, client_ord_id='CTadv', contractor_ord_id='CTexec',
                            final_ord_id='CTfinal')
    check(schemas, 'CreateInitialContractRequest', body)


def test_initial_contract_requires_final_contract_id(schemas):
    """`finalContractId` обязателен по спеке: изначальный всегда создаётся прикреплённым
    к доходному. Это и есть подтверждение нашей M:N — форму схемы задал сам API."""
    assert 'finalContractId' in schemas['CreateInitialContractRequest']['required']


def test_contract_type_absent_from_api_is_refused():
    """Тип, которого API не принимает на создание, до отправки не доходит.

    `VirtualFinalContract` в спеке отсутствует вовсе, `SelfPromotionContract` и
    `EcidContract` читаются, но не создаются. Раньше все три числились у нас
    отправляемыми.
    """
    for kind in ('VirtualFinalContract', 'SelfPromotionContract', 'EcidContract'):
        initial = SimpleNamespace(id=3, number='X', date=date(2025, 1, 1), type=kind,
                                  subject_type=None, action_type=None)
        with pytest.raises(OrdPayloadError) as e:
            initial_contract(initial, 'a', 'b', 'c')
        assert 'не принимает на создание' in str(e.value)


def test_missing_data_is_named_not_guessed():
    """Пустое поле называется по имени, а не подставляется похожим."""
    contract = SimpleNamespace(id=9, contract_number='', contract_date=None)
    with pytest.raises(OrdPayloadError) as e:
        final_contract(contract, 'CTclient')
    assert 'дата договора' in str(e.value)
