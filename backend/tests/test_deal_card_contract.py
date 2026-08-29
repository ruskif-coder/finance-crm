"""
Заполненность карточки договора — задача 9 (карточка сделки по дизайн-хендоффу).

`_contract_fill` (app/routers/ord.py) — призыв аккаунту дозаполнить договор в реестре,
не проверка на входе: без CONTRACT_FILL_FIELDS ЕРИД не выпустить и акт не сдать, но
узнаётся это через месяц, на сдаче. Шкала без перечня недостающих полей вырождается
в «что-то не так» — на это не реагируют, поэтому и `missing` в ответе, а не только
число. Пустота в базе записана и NULL-ом, и пустой строкой — обе обязаны считаться
незаполненным полем: живьём измерено (26.08.2026, 37 помеченных договоров) номер
37/37, ИНН 37/37, дата 36/37, адрес 26/37, срок оплаты 17/37, условие оплаты 1/37 —
разброс между полями означает, что где-то пустота записана одним способом, где-то
другим, и разное поведение на них дало бы разную (неверную) картину.

Тот же приём фиктивных строк и очистки по префиксу, что и в соседних test_ord_*.py
(прочитаны перед тем, как это писать) — прежде всего test_ord_matching.py и
test_ord_http.py.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.ord.models import OrdInitialContract, OrdInitialFinalLink
from app.routers.ord import _contract_fill, deal_assembly
from app.sales.models import SalesDeal

TEST_ORD_PREFIX = 'CTfillcard'
TEST_INNS = ('7700000051', '7700000052', '7700000053')
TEST_INN_OWN = '7700000053'   # фиктивное «второе своё юрлицо», см. тест про ставку НДС

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'))


def _purge(db):
    """Снести сделку/связи/договоры/изначальные/контрагентов этого файла.

    Вызывается и до, и после теста — до ловит мусор прошлого упавшего прогона,
    после убирает свой собственный. Порядок важен: SalesDeal ссылается на
    OrdInitialContract внешним ключом, Contract/OrdInitialFinalLink — на
    OrdInitialContract.
    """
    db.rollback()
    db.query(SalesDeal).filter(
        SalesDeal.bitrix_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    initial_ids = [r.id for r in db.query(OrdInitialContract.id)
                   .filter(OrdInitialContract.ord_id.like(f'{TEST_ORD_PREFIX}%')).all()]
    if initial_ids:
        db.query(OrdInitialFinalLink).filter(
            OrdInitialFinalLink.initial_contract_id.in_(initial_ids)
        ).delete(synchronize_session=False)
        db.query(OrdInitialContract).filter(
            OrdInitialContract.id.in_(initial_ids)
        ).delete(synchronize_session=False)
    db.query(Contract).filter(
        Contract.ord_contract_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    db.query(Counterparty).filter(Counterparty.inn.in_(TEST_INNS)
                                  ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def db():
    """Настоящая сессия (app.database.SessionLocal) на рабочей базе.

    TEST_INNS обязаны не совпадать ни с одним реальным контрагентом — иначе тест
    считал бы заполненность по чужому, боевому договору. Проверка идёт ДО очистки
    (находка I6 в соседних test_ord_matching.py/test_ord_http.py).
    """
    session = SessionLocal()
    clash = session.query(Counterparty.inn).filter(Counterparty.inn.in_(TEST_INNS)).all()
    assert not clash, f"фиктивные ИНН {TEST_INNS} заняты реальными контрагентами {clash}"
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _make_counterparty(db, inn, name, address=None):
    cp = Counterparty(name=name, inn=inn, address=address)
    db.add(cp)
    db.flush()
    return cp


def test_fill_counts_all_six_and_names_what_is_missing(db):
    """Шкала заполненности обязана называть, чего именно нет.

    Без перечня она превращается в «что-то не так» — на это не реагируют.
    """
    cp = _make_counterparty(db, TEST_INNS[0], f'{TEST_ORD_PREFIX} Контрагент Частичный',
                            address='г. Москва, ул. Тестовая, 1')
    contract = Contract(
        counterparty_id=cp.id, ord_contract_id=f'{TEST_ORD_PREFIX}-final-partial',
        contract_number='ТД-01/2026', contract_date=date(2026, 1, 10), inn=TEST_INNS[0],
        payment_term_days=None, payment_term_condition=None,
    )
    db.add(contract)
    db.flush()

    filled, total, missing = _contract_fill(db, contract)

    assert total == 6, "полей должно быть ровно шесть — CONTRACT_FILL_FIELDS"
    assert filled == 4, "заполнены номер/дата/ИНН/адрес, не хватает срока и условия оплаты"
    assert 'срок оплаты' in missing
    assert 'условие оплаты' in missing
    assert 'номер договора' not in missing
    assert 'ИНН контрагента' not in missing
    assert 'адрес контрагента' not in missing
    assert 'дата договора' not in missing


def test_empty_string_counts_as_missing_same_as_none(db):
    """Пустота записана в базе и NULL-ом, и пустой строкой — обе обязаны считаться
    незаполненным полем, иначе шкала покажет заполненным поле, которого нет на самом
    деле (см. докстринг модуля: живой разброс 37/37 vs 1/37 по разным полям —
    признак, что оба вида пустоты уже встречаются в базе).

    counterparty_id=None (контрагент не привязан вовсе) — заодно проверяет, что
    ветка __address не падает и адрес честно считается отсутствующим, а не пропускается.
    """
    contract = SimpleNamespace(
        counterparty_id=None, contract_number='', contract_date=None, inn='',
        payment_term_days=None, payment_term_condition='',
    )
    filled, total, missing = _contract_fill(db, contract)

    assert total == 6
    assert filled == 0, "пустая строка не должна засчитываться как заполненное поле"
    assert 'номер договора' in missing
    assert 'ИНН контрагента' in missing
    assert 'условие оплаты' in missing
    assert 'адрес контрагента' in missing, "counterparty_id=None -> контрагент не найден -> адрес пуст"


def test_fully_filled_contract_reports_no_missing_fields(db):
    """Все шесть полей на месте — явный положительный ответ, не пустая строка."""
    cp = _make_counterparty(db, TEST_INNS[1], f'{TEST_ORD_PREFIX} Контрагент Полный',
                            address='г. Москва, ул. Полная, 2')
    contract = Contract(
        counterparty_id=cp.id, ord_contract_id=f'{TEST_ORD_PREFIX}-final-full',
        contract_number='ТД-02/2026', contract_date=date(2026, 2, 1), inn=TEST_INNS[1],
        payment_term_days=30, payment_term_condition='С даты УПД',
    )
    db.add(contract)
    db.flush()

    filled, total, missing = _contract_fill(db, contract)

    assert (filled, total) == (6, 6)
    assert missing == 'карточка заполнена'


def test_contract_fill_is_none_without_a_contract(db):
    """Ступени, у которых нашей строки в contracts нет вовсе (см. deal_assembly —
    изначальный договор без своей карточки в реестре), не получают "0 из 6" —
    заполненность у них не считается совсем."""
    assert _contract_fill(db, None) is None


def test_deal_assembly_exposes_fill_for_final_and_none_for_unmatched_initial(db):
    """Ступень 2 (доходный) — всегда наша строка в contracts, заполненность
    считается. Ступень 3 (изначальный) — сущность зеркала ОРД (OrdInitialContract),
    не наш реестр: своей карточки нет, если её отдельно не пометили тем же
    ord_contract_id — тогда fill остаётся None, а не "0 из 6".
    """
    cp = _make_counterparty(db, TEST_INNS[0], f'{TEST_ORD_PREFIX} Контрагент Сборки',
                            address='г. Москва, ул. Сборочная, 3')
    final_contract = Contract(
        counterparty_id=cp.id, ord_contract_id=f'{TEST_ORD_PREFIX}-assembly-final',
        ord_kind='final', contract_number='ТД-АСМ/2026',
        contract_date=date(2026, 3, 1), inn=TEST_INNS[0],
        payment_term_days=45, payment_term_condition='С даты АКТ',
    )
    db.add(final_contract)
    db.flush()

    initial = OrdInitialContract(ord_id=f'{TEST_ORD_PREFIX}-assembly-initial', date=date(2025, 1, 1))
    db.add(initial)
    db.flush()
    db.add(OrdInitialFinalLink(initial_contract_id=initial.id,
                               final_ord_id=final_contract.ord_contract_id))
    db.flush()

    deal = SalesDeal(bitrix_id=f'{TEST_ORD_PREFIX}-assembly-1', payer_counterparty_id=cp.id,
                     payer_name=None, ord_initial_contract_id=initial.id)
    db.add(deal)
    db.flush()

    result = deal_assembly(deal.id, db=db, current_user=_FAKE_ADMIN)

    assert result['final']['fill'] is not None
    assert result['final']['fill'][:2] == [6, 6]
    assert result['initial']['fill'] is None, (
        "изначальный договор здесь не отмечен отдельной строкой в contracts — "
        "заполненность не должна была найтись"
    )


def test_vat_rate_comes_from_the_single_own_company(db):
    """Ставку НДС по нашим услугам даёт наше юрлицо, и только пока оно одно.

    Правило владельца (26.08.2026): «у нас есть наше юрлицо, от которого работаем,
    и оно регулирует ставку НДС по нашим услугам». До этого в карточке сделки жила
    константа 0.22 — в трёх местах десктопа и ещё в двух мобильной версии.

    Пин именно на «ровно одно, иначе не знаем», а не на «первое попавшееся»:
    сократить это до `.first()` выглядит безобидным упрощением, но в этом проекте
    ровно такая догадка внутри строгого на вид кода уже дала неверный результат
    (сведение номеров договоров в app/ord/importer.py). Со вторым своим юрлицом
    ставка перестаёт быть свойством компании и становится свойством платёжного
    договора сделки — и молча взятая чужая ставка хуже честного прочерка.
    """
    from app.routers.sales_dashboard import _own_company_out

    one = _own_company_out(db)
    assert one is not None, (
        "своё юрлицо не одно — карточка сделки перестала знать ставку НДС; "
        "это не поломка теста: ставку пора брать от юрлица платёжного договора"
    )
    assert 'vat_rate_income' in one, (
        "ставка читается из vat_rate_income; vat_rate заморожен "
        "(см. routers/counterparties.py) и остался от одноставочной схемы"
    )

    db.add(Counterparty(name=f'{TEST_ORD_PREFIX} второе своё юрлицо',
                        inn=TEST_INN_OWN, is_own_company=True))
    db.commit()
    assert _own_company_out(db) is None, (
        "со вторым своим юрлицом ставка неоднозначна — функция обязана вернуть None, "
        "а не выбрать одно из двух"
    )


def test_every_consumer_refuses_together_when_own_company_is_ambiguous(db):
    """Все потребители отвечают про наше юрлицо ОДНО И ТО ЖЕ.

    Пин не на значение, а на согласие. До 26.08.2026 правил было два: автоштамп
    операций брал `ORDER BY id LIMIT 1`, карточка сделки отказывалась выбирать.
    Пока юрлицо одно, оба дают один ответ, и расхождение невидимо — оно проявилось
    бы только со вторым юрлицом и только на данных, которые уже записаны.

    Поэтому здесь второе юрлицо заводится нарочно: при неоднозначности молчать
    обязаны ВСЕ. Один потребитель, вернувшийся к догадке, покрасит этот тест —
    в отличие от простого «функция возвращает None», которое переживает
    появление второй копии правила в другом файле.
    """
    from app import own_company
    from app.routers.sales_dashboard import _own_company_out

    assert own_company.sole_id(db) == (_own_company_out(db) or {}).get('id'), (
        "потребители уже расходятся при ОДНОМ юрлице"
    )

    db.add(Counterparty(name=f'{TEST_ORD_PREFIX} второе своё юрлицо',
                        inn=TEST_INN_OWN, is_own_company=True))
    db.commit()

    assert len(own_company.all_own(db)) == 2, "фиктивное юрлицо не завелось — тест ничего не проверил"
    assert own_company.sole(db) is None
    assert own_company.sole_id(db) is None, (
        "автоштамп операций снова угадывает юрлицо: пустое own_company_id видно "
        "и лечится, тихо проставленное чужое — нет"
    )
    assert own_company.public(db) is None
    assert _own_company_out(db) is None
