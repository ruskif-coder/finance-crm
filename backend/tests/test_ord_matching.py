"""
Подбор договоров ОРД для сделки.

Измерено 25.08.2026: когда плательщик известен, доходный договор определяется
однозначно ВСЕГДА — 305 случаев из 305. Поэтому неоднозначность здесь не «редкий
случай», а сигнал, что данные поехали, и она обязана быть видимой, а не
разрешаться молча взятием первого.

Обоснование выбора — не украшение. Наш рекламодатель с юрлицом ОРД не связан
(решение владельца), поэтому совпадение по имени это догадка: сходятся 24 из 91.
Человек, подтверждающий подстановку, должен видеть, откуда она взялась.
"""
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.ord.matching import (_explain_ambiguous, _explain_last_used, _explain_name_match,
                              _explain_none, _explain_single, _last_used_initial, parse_payer,
                              propose_initial, resolve_final)
from app.ord.models import OrdInitialContract, OrdInitialFinalLink
from app.routers.ord import deal_assembly
from app.sales.models import SalesAdvertiser, SalesAgency, SalesDeal


def test_payer_is_the_tail_after_the_slash():
    """Метка сделки составная: «агентство / плательщик»."""
    assert parse_payer('Альфа Медиа / Медиана Би Эйч') == 'Медиана Би Эйч'
    assert parse_payer('Бета Групп / СЛ Медиа') == 'СЛ Медиа'


def test_label_without_slash_has_no_payer():
    """«Bright Wave Group» — агентство, а не юрлицо.

    Вернуть его как плательщика значит искать договор по названию группы и не найти.
    Пользователь при этом увидит «плательщик не определён» вместо «договора нет» —
    это две разные подсказки, и путать их нельзя.
    """
    assert parse_payer('Bright Wave Group (Брайт Вэйв Групп)') is None
    assert parse_payer('Bluewind Media (Блювинд Медиа)') is None


def test_blank_payer():
    assert parse_payer('') is None
    assert parse_payer(None) is None
    assert parse_payer('   ') is None


def test_several_slashes_take_the_last_part():
    assert parse_payer('A / B / Финальное Юрлицо') == 'Финальное Юрлицо'


def test_reason_names_the_source_of_the_guess():
    """Обоснование обязано различать «помню прошлый выбор» и «догадался по имени».

    Это разные степени уверенности. Совпадение по имени срабатывает у 24 из 91 —
    на нём нельзя останавливаться молча.
    """
    assert 'прошлый раз' in _explain_last_used('ТД-01/2025', 2, 'A-1234', '12.08.2026')
    guess = _explain_name_match('ТД-01/2025', 2, 'Тестовый бренд')
    assert 'догадка' in guess.lower() and 'проверьте' in guess.lower()


def test_single_candidate_reads_as_certainty():
    text = _explain_single('ТД-01/2025', 'Тестовый бренд')
    assert 'единственный' in text.lower() and 'ТД-01/2025' in text


def test_ambiguous_asks_instead_of_choosing():
    """Два кандидата и никаких подсказок — предложения нет, есть список.

    Подставить первый попавшийся значит отправить в ЕРИР рекламу не того
    рекламодателя. Таких пар девять из 134.
    """
    assert 'выберите' in _explain_ambiguous('ТД-01/2025', 2).lower()


def test_no_candidates_names_the_contract():
    """Часть доходных не имеет ни одного изначального — сообщение должно это сказать."""
    text = _explain_none('ТД-02/2025')
    assert 'ТД-02/2025' in text and 'нет' in text.lower()


# ── resolve_final / propose_initial: тесты с настоящей сессией БД ───────────
#
# Всё выше проверяет только строковые _explain_*/parse_payer — ни resolve_final,
# ни propose_initial ни разу не вызваны с базой. Главная гарантия обеих функций —
# неоднозначность не разрешается молча (см. докстринг модуля выше) — на боевых
# данных ни разу не сработала (0 ambiguous из 899), а значит подтверждена только
# чтением кода, не измерением. Шесть тестов ниже гоняют обе функции (и
# _last_used_initial отдельно — регрессия на сортировку id vs date_create) на
# настоящей Postgres-сессии тем же приёмом, что db/_purge_ord_test_rows в
# соседнем test_ord_import.py (прочитан целиком перед тем, как это писать).
#
# База рабочая (126 изначальных / 150 связей / 899 сделок / 173 договора боевых
# данных на момент написания) — используются только вымышленные CTtest*-номера
# и ИНН серии 77000000xx, и всё созданное убирается в фикстуре `db`.
# `deal`, которого просят resolve_final/propose_initial, нужен им не как
# ORM-строка, а как утиный тип с несколькими полями (payer_counterparty_id/
# payer_name/agency_id/advertiser_id/id) — там, где этого достаточно, тесты
# берут SimpleNamespace вместо настоящей sales_deals. Единственное исключение —
# test_last_used_initial_prefers_date_over_id: сама проверяемая сортировка живёт
# в запросе к sales_deals, и без настоящих строк там измерить нечего.

TEST_ORD_PREFIX = 'CTtest'
TEST_INNS = ('7700000031', '7700000032')


def _purge_matching_test_rows(db):
    """Снести CTtest*-строки и фиктивных плательщиков этого файла.

    Вызывается и до, и после теста — до ловит мусор прошлого упавшего прогона,
    после убирает свой собственный (тот же приём, что в test_ord_import.py).
    Порядок важен: SalesDeal ссылается на OrdInitialContract/SalesAgency/
    SalesAdvertiser внешними ключами, поэтому её строки уходят первыми.
    """
    db.rollback()
    db.query(SalesDeal).filter(
        SalesDeal.bitrix_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    initial_ids = [r.id for r in db.query(OrdInitialContract.id)
                   .filter(OrdInitialContract.ord_id.like(f'{TEST_ORD_PREFIX}%')).all()]
    db.query(OrdInitialFinalLink).filter(
        OrdInitialFinalLink.final_ord_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
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
    db.query(SalesAgency).filter(
        SalesAgency.name.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    db.query(SalesAdvertiser).filter(
        SalesAdvertiser.name.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def db():
    """Настоящая сессия (app.database.SessionLocal) на рабочей базе.

    TEST_INNS обязаны не совпадать ни с одним реальным контрагентом — иначе
    resolve_final нашёл бы плательщику этого теста реальные, боевые договоры
    вместо фиктивных строк, которые заводит сам тест.

    Находка ревью I6: проверка обязана идти ДО очистки, не после. «Сначала
    почистить, потом проверить» гарантированно не находит клэша, даже если он
    был, — к моменту assert-а страховка уже снесла всё, включая настоящего
    контрагента, который просто оказался тёзкой по ИНН: «если бы были заняты —
    их бы уже удалили». Проверка идёт на состоянии базы ДО очистки.
    """
    session = SessionLocal()
    clash = session.query(Counterparty.inn).filter(Counterparty.inn.in_(TEST_INNS)).all()
    assert not clash, (
        f"фиктивные ИНН {TEST_INNS} заняты реальными контрагентами {clash} — "
        f"возьми другую фиктивную серию"
    )
    _purge_matching_test_rows(session)
    try:
        yield session
    finally:
        _purge_matching_test_rows(session)
        session.close()


def _make_payer(db, inn, name):
    cp = Counterparty(name=name, inn=inn)
    db.add(cp)
    db.flush()
    return cp


def _make_final_contract(db, counterparty_id, ord_contract_id, number=None):
    c = Contract(counterparty_id=counterparty_id, ord_contract_id=ord_contract_id,
                ord_kind='final', contract_number=number)
    db.add(c)
    db.flush()
    return c


def test_last_used_initial_prefers_date_over_id(db):
    """Находка ревью 25.08.2026: id сделки отражает порядок синхронизации с
    Битриксом, а не хронологию — измерено 822 инверсии из 899 (91%) между
    порядком id и порядком date_create. Заводим ровно такую инверсию: сделка,
    вставленная ПЕРВОЙ (меньший id), получает более позднюю date_create, а
    вставленная ВТОРОЙ (больший id) — более раннюю. _last_used_initial обязана
    взять ту, что позже по дате, а не ту, что с большим номером.
    """
    agency = SalesAgency(name=f'{TEST_ORD_PREFIX} Агентство Порядка')
    advertiser = SalesAdvertiser(name=f'{TEST_ORD_PREFIX} Рекламодатель Порядка')
    db.add_all([agency, advertiser])
    db.flush()

    initial_old = OrdInitialContract(ord_id=f'{TEST_ORD_PREFIX}-init-order-old',
                                     date=date(2024, 1, 1))
    initial_new = OrdInitialContract(ord_id=f'{TEST_ORD_PREFIX}-init-order-new',
                                     date=date(2024, 1, 1))
    db.add_all([initial_old, initial_new])
    db.flush()

    # Вставлена первой -> меньший id, но дата ПОЗЖЕ.
    deal_low_id = SalesDeal(bitrix_id=f'{TEST_ORD_PREFIX}-order-low-id',
                            agency_id=agency.id, advertiser_id=advertiser.id,
                            ord_initial_contract_id=initial_new.id,
                            date_create=datetime(2026, 6, 1))
    db.add(deal_low_id)
    db.flush()
    # Вставлена второй -> больший id, но дата РАНЬШЕ — инверсия, ради которой тест.
    deal_high_id = SalesDeal(bitrix_id=f'{TEST_ORD_PREFIX}-order-high-id',
                             agency_id=agency.id, advertiser_id=advertiser.id,
                             ord_initial_contract_id=initial_old.id,
                             date_create=datetime(2025, 1, 1))
    db.add(deal_high_id)
    db.flush()
    assert deal_high_id.id > deal_low_id.id, "инверсия id/даты не завелась — тест ничего не проверяет"

    # id=-1 — заведомо не совпадает ни с одной настоящей сделкой, id != deal.id
    # в _last_used_initial не отфильтрует ни deal_low_id, ни deal_high_id.
    current = SimpleNamespace(id=-1, agency_id=agency.id, advertiser_id=advertiser.id)
    result = _last_used_initial(db, current)

    assert result == initial_new.id, (
        "взят изначальный по сделке с большим id, а не по более поздней дате — "
        "сортировка снова уехала на id.desc()"
    )


def test_resolve_final_two_marked_contracts_is_ambiguous_not_a_guess(db):
    """Два договора с отметкой ОРД у одного плательщика — вопрос человеку, а не
    выбор наугад. Подставить первый попавшийся значит отправить в ЕРИР не тот
    договор — это и есть находка ревью: до сих пор эта ветка была подтверждена
    только чтением кода, ни разу — измерением на реальном запросе к базе.
    """
    cp = _make_payer(db, TEST_INNS[0], f'{TEST_ORD_PREFIX} Плательщик Один')
    _make_final_contract(db, cp.id, f'{TEST_ORD_PREFIX}-final-amb-1', 'ТД-А/2026')
    _make_final_contract(db, cp.id, f'{TEST_ORD_PREFIX}-final-amb-2', 'ТД-Б/2026')

    deal = SimpleNamespace(payer_counterparty_id=cp.id, payer_name=None)
    result = resolve_final(db, deal)

    assert result.reason_code == 'ambiguous'
    assert result.contract is None
    assert len(result.candidates) == 2
    assert 'выберите' in result.reason.lower()


def test_resolve_final_single_marked_contract_is_ok_and_names_it(db):
    """Ровно один договор с отметкой ОРД — уверенный ответ с номером договора."""
    cp = _make_payer(db, TEST_INNS[1], f'{TEST_ORD_PREFIX} Плательщик Два')
    contract = _make_final_contract(db, cp.id, f'{TEST_ORD_PREFIX}-final-ok-1',
                                    'ТД-СТ-1/2026')

    deal = SimpleNamespace(payer_counterparty_id=cp.id, payer_name=None)
    result = resolve_final(db, deal)

    assert result.reason_code == 'ok'
    assert result.contract is not None and result.contract.id == contract.id
    assert 'ТД-СТ-1/2026' in result.reason


def test_resolve_final_returns_payer_even_when_deal_label_is_blank(db):
    """Находка на бою: связь с контрагентом-плательщиком есть, а payer_name у
    сделки пуст (ровно так у сделок 2471/2470) — resolve_final обязана вернуть
    найденного контрагента через новое поле `payer`, а не оставить его пустым.
    Экран берёт имя ступени «Плательщик» отсюда; до фикса там рисовалось
    буквально «null», потому что роутер брал имя из пустой метки сделки.
    """
    cp = _make_payer(db, TEST_INNS[0], f'{TEST_ORD_PREFIX} Плательщик Без Метки')
    _make_final_contract(db, cp.id, f'{TEST_ORD_PREFIX}-final-blank-label-1',
                         'ТД-БМ-1/2026')

    deal = SimpleNamespace(payer_counterparty_id=cp.id, payer_name=None)
    result = resolve_final(db, deal)

    assert result.payer is not None
    assert result.payer.id == cp.id
    assert result.payer.name, "payer найден, но имя пустое — экран снова покажет null"


def test_resolve_final_prefers_counterparty_over_mismatched_deal_label(db):
    """Находка на бою: метка сделки и найденный контрагент расходятся — ровно так
    у сделок 48/49, где payer_name нёс название АГЕНТСТВА, а payer_counterparty_id
    указывал на настоящего плательщика. `_payer_counterparty` смотрит на связь
    раньше метки (см. её докстринг), поэтому наружу обязан уйти контрагент, а не
    метка: показать метку на ступени «Плательщик» значило бы подставить агентство
    вместо юрлица-плательщика, даже когда метка непустая.
    """
    cp = _make_payer(db, TEST_INNS[1], f'{TEST_ORD_PREFIX} Плательщик Настоящий')
    _make_final_contract(db, cp.id, f'{TEST_ORD_PREFIX}-final-mismatch-1',
                         'ТД-НС-1/2026')

    agency_label = f'{TEST_ORD_PREFIX} Агентство-Метка (агентство)'
    deal = SimpleNamespace(payer_counterparty_id=cp.id, payer_name=agency_label)
    result = resolve_final(db, deal)

    assert result.payer is not None
    assert result.payer.name == cp.name
    assert result.payer.name != agency_label


_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'))


def test_deal_assembly_payer_uses_resolved_counterparty_not_raw_deal_fields(db):
    """Регрессия на сам баг с боя (сделки 48/49): проверяет РОУТЕР `deal_assembly`,
    а не только resolve_final — два теста выше гоняют resolve_final напрямую и не
    заметили бы, откати роутер обратно на `'name': deal.payer_name`. Метка сделки
    здесь нарочно другая, как у настоящих 48/49 (несёт название агентства), — если
    роутер возьмёт имя из deal.payer_name напрямую, этот тест падает.

    current_user — фиктивный админ (SimpleNamespace с role.key='admin'): этого
    достаточно для _assert_deal_in_scope (admin выходит из проверки раньше, чем
    та тронет что-либо ещё в user), а настоящий User/Role здесь не по делу теста.
    """
    cp = _make_payer(db, TEST_INNS[0], f'{TEST_ORD_PREFIX} Плательщик РоутерТест')
    _make_final_contract(db, cp.id, f'{TEST_ORD_PREFIX}-final-router-1', 'ТД-РТ-1/2026')

    agency_label = f'{TEST_ORD_PREFIX} Агентство-Метка Роутер (агентство)'
    deal = SalesDeal(bitrix_id=f'{TEST_ORD_PREFIX}-router-1',
                     payer_counterparty_id=cp.id, payer_name=agency_label)
    db.add(deal)
    db.flush()

    result = deal_assembly(deal.id, db=db, current_user=_FAKE_ADMIN)

    assert result['payer']['ok'] is True
    assert result['payer']['counterparty_id'] == cp.id
    assert result['payer']['name'] == cp.name
    assert result['payer']['name'] != agency_label


def test_resolve_final_no_payer_does_not_touch_contracts(db):
    """Плательщика нет вовсе — reason_code no_payer, и до таблицы договоров
    дело не доходит: _payer_counterparty возвращает причину раньше, чем
    resolve_final успевает сделать хоть один db.query(Contract).

    Проверяется не только по коду (структурно это и так гарантировано ранним
    return), а измерением: подменяем db.query шпионом и убеждаемся, что среди
    вызванных моделей Contract нет ни разу.
    """
    queried_models = []
    orig_query = db.query

    def _spy(*models, **kw):
        queried_models.extend(models)
        return orig_query(*models, **kw)

    db.query = _spy
    try:
        deal = SimpleNamespace(payer_counterparty_id=None, payer_name=None)
        result = resolve_final(db, deal)
    finally:
        db.query = orig_query

    assert result.reason_code == 'no_payer'
    assert result.contract is None
    assert result.candidates == []
    assert Contract not in queried_models


def test_propose_initial_two_candidates_no_memory_is_ambiguous(db):
    """Под доходным два изначальных, прошлых сборок для этой пары агентство ×
    рекламодатель нет — предложения нет, есть список на выбор человеку."""
    initial_a = OrdInitialContract(ord_id=f'{TEST_ORD_PREFIX}-init-amb-1',
                                   date=date(2025, 1, 10), advertiser_name='Рекламодатель А')
    initial_b = OrdInitialContract(ord_id=f'{TEST_ORD_PREFIX}-init-amb-2',
                                   date=date(2025, 2, 10), advertiser_name='Рекламодатель Б')
    db.add_all([initial_a, initial_b])
    db.flush()
    final_ord_id = f'{TEST_ORD_PREFIX}-final-doh-amb'
    db.add_all([
        OrdInitialFinalLink(initial_contract_id=initial_a.id, final_ord_id=final_ord_id),
        OrdInitialFinalLink(initial_contract_id=initial_b.id, final_ord_id=final_ord_id),
    ])
    db.flush()

    # agency_id/advertiser_id не заданы — _last_used_initial гарантированно без
    # памяти (см. её докстринг: пара обязана быть известна целиком).
    deal = SimpleNamespace(id=None, agency_id=None, advertiser_id=None)
    result = propose_initial(db, deal, final_ord_id)

    assert result.reason_code == 'ambiguous'
    assert result.contract is None
    assert len(result.candidates) == 2
    assert 'выберите' in result.reason.lower()


def test_propose_initial_zero_candidates_is_none(db):
    """Под доходным нет ни одного изначального договора — сообщение должно
    это назвать, а не молчать и не падать."""
    deal = SimpleNamespace(id=None, agency_id=None, advertiser_id=None)
    result = propose_initial(db, deal, f'{TEST_ORD_PREFIX}-final-doh-none')

    assert result.reason_code == 'none'
    assert result.contract is None
    assert result.candidates == []
