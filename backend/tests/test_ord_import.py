"""
Разбор выгрузок кабинета ОРД в зеркало.

Проверяется то, что ломается молча: подпись типа договора, которую не узнали
(строка уедет в ОРД неверной), повторный прогон того же файла (обязан обновлять,
а не плодить), и связь одного изначального договора с несколькими доходными —
ради неё и переделывалась схема.

Файлы-образцы собираются в тесте из openpyxl, а не лежат в репозитории: настоящие
выгрузки содержат имена реальных контрагентов, и в git им не место.
"""
import io

import pytest

pytest.importorskip("pandas")
from openpyxl import Workbook                                    # noqa: E402

from app.database import SessionLocal                            # noqa: E402
from app.models import Contract, Counterparty                    # noqa: E402
from app.ord import importer                                     # noqa: E402
from app.ord.models import OrdFinalMirror, OrdInitialContract, OrdInitialFinalLink  # noqa: E402

INITIAL_HEADER = [
    'Id изначального договора', 'Cid изначального договора',
    'Рекламодатель ИНН/Номер налогоплательщика/Регистрационный номер', 'Рекламодатель',
    'Исполнитель ИНН/Номер налогоплательщика/Регистрационный номер', 'Исполнитель',
    'Номер изначального договора', 'Дата изначального договора',
    'Дата окончания срока действия договора', 'Стоимость услуг по договору',
    'Тип договора', 'Вид договора', 'Вид деятельности посреднического договора',
    'Агент действует', 'Id доп. соглашения', 'Cid доп.соглашения',
    'Номер изначального доп.соглашения', 'Дата изначального доп.соглашения',
    'Дата окончания срока действия ДС', 'Стоимость услуг по договору доп.соглашения',
    'Статус изначального договора', 'Дата статуса изначального договора', 'Текст ошибки',
    'Статус доп. соглашения', 'Дата статуса доп. соглашения', 'Текст ошибки доп. соглашения',
    'ИНН заказчика', 'Заказчик', 'Id доходного договора', 'Номер доходного договора',
]
INITIAL_ROW = [
    'CTtest0000000000000001AA', '11111111-2222-3333-4444-555555555555',
    '7700000001', 'Акционерное общество «Тестовый рекламодатель»',
    '7700000002', 'ООО «Тестовое агентство»',
    '1', '01.02.2025', '', 0,
    'Посреднический договор', 'Посредничество', 'Заключение договоров',
    'В интересах РД', '', '', '', '', '', '',
    'Зарегистрирован', '17.06.2025 13:48', '', '', '', '',
    '7700000003', 'ООО «Тестовый заказчик»', 'CTtest0000000000000002BB', 'ТД-01/2025',
]


def _book(sheet_name, header, rows, extra_sheet=None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(header)
    for r in rows:
        ws.append(r)
    if extra_sheet:
        name, hdr, body = extra_sheet
        s = wb.create_sheet(name)
        s.append(hdr)
        for r in body:
            s.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_initial_row_is_parsed_into_codes():
    """Подписи кабинета переводятся в коды API — в базе живёт код."""
    data = _book('Изначальные договоры', INITIAL_HEADER, [INITIAL_ROW])
    rows = importer.parse_initial(data)
    assert len(rows) == 1
    r = rows[0]
    assert r['ord_id'] == 'CTtest0000000000000001AA'
    assert r['type'] == 'MediationContract'
    assert r['subject_type'] == 'Mediation'
    assert r['action_type'] == 'Contracting'
    assert r['is_agent_acting_for_publisher'] is True
    assert r['client_inn'] == '7700000001'
    assert r['contractor_inn'] == '7700000002'
    assert r['final_ord_id'] == 'CTtest0000000000000002BB'
    assert r['date'].isoformat() == '2025-02-01'


def test_unknown_type_label_is_reported_not_guessed():
    """Незнакомая подпись обязана попасть в список пропущенных, а не подставиться.

    Молча подставленный «похожий» вид договора уедет в ЕРИР и всплывёт у проверяющего.
    """
    row = list(INITIAL_ROW)
    row[10] = 'Договор поставки'
    rows = importer.parse_initial(_book('Изначальные договоры', INITIAL_HEADER, [row]))
    assert rows[0]['type'] is None
    assert 'Договор поставки' in rows[0]['warnings'][0]


def test_inn_with_excel_float_tail_is_cleaned():
    """Excel отдаёт ИНН числом, и он приезжает как 7700000001.0."""
    row = list(INITIAL_ROW)
    row[2] = 7700000001
    rows = importer.parse_initial(_book('Изначальные договоры', INITIAL_HEADER, [row]))
    assert rows[0]['client_inn'] == '7700000001'


def test_sheet_name_must_match_because_the_cabinet_fixes_it():
    """Лист называется кабинетом, а не пользователем: имя фиксировано.

    В отличие от импорта операций, где лист выбирается по содержимому, здесь файл
    приходит из чужой системы неизменённым — и подмена листа означала бы, что
    загрузили не тот файл.
    """
    with pytest.raises(ValueError) as e:
        importer.parse_initial(_book('Лист1', INITIAL_HEADER, [INITIAL_ROW]))
    assert 'Изначальные договоры' in str(e.value)


def test_empty_number_is_kept_as_none_not_empty_string():
    """У 6 из 152 договоров номера нет вовсе — пустота одна, а не две."""
    row = list(INITIAL_ROW)
    row[6] = ''
    rows = importer.parse_initial(_book('Изначальные договоры', INITIAL_HEADER, [row]))
    assert rows[0]['number'] is None


def test_one_initial_contract_can_hang_under_several_finals():
    """Ровно тот случай, ради которого переделывалась схема.

    В выгрузке одна и та же строка договора повторяется с разными доходными.
    Схема с одной колонкой final_contract_id теряла на этом 24 связи из 150.
    """
    row_a = list(INITIAL_ROW)
    row_b = list(INITIAL_ROW)
    row_b[28] = 'CTtest0000000000000003CC'      # другой Id доходного
    row_b[29] = 'ТД-02/2025'
    rows = importer.parse_initial(_book('Изначальные договоры', INITIAL_HEADER,
                                        [row_a, row_b]))
    assert len({r['ord_id'] for r in rows}) == 1
    assert len({r['final_ord_id'] for r in rows}) == 2


def test_contract_number_matching_folds_lookalike_letters():
    """`PM` латиницей и `РМ` кириллицей — один и тот же договор.

    В кабинете ОРД пишут и так, и так, плюс пробел вместо дефиса. Без сведения
    сходилось 28 договоров из 52, со сведением 36.
    """
    from app.ord.importer import _fold
    assert _fold('PM-05-12-2023') == _fold('РМ 05-12-2023')
    assert _fold('ДГ15-05-24') == _fold('ДГ 15-05-24')
    assert _fold('PM-01-06-26') != _fold('PM-01-06-26-1')


# ── upsert(): тесты с настоящей сессией БД ──────────────────────────────────
#
# У upsert() до сих пор не было ни одного теста, что пишет в базу — семь тестов выше
# гоняют только parse_*/_fold. Здесь — три вещи, ради которых менялась схема (см.
# докстринг модуля и upsert()), и которые parse-тест в принципе не ловит:
# идемпотентность повторного прогона, схлопывание нескольких строк выгрузки с одним
# Id изначального договора в одну запись с несколькими связями, и порядок обработки
# (доходные/расходные раньше изначальных — иначе связь не находит наш договор).
#
# База — рабочая (126 изначальных / 150 связей боевых данных на момент написания),
# поэтому используются только вымышленные CTtest*-идентификаторы и ИНН серии
# 77000000xx (тот же приём, что и в фикстурах выше), и всё созданное убирается в
# фикстуре `db`.

TEST_ORD_PREFIX = 'CTtest'
TEST_INNS = ('7700000001', '7700000002', '7700000009')
TEST_CONTRACT_INN = '7700000009'   # ИНН договора-заглушки для теста на порядок обработки
TEST_CONTRACT_NUMBER = 'ТД-99/2025'   # её номер — матчинг теперь только по номеру, не по ИНН

FINAL_HEADER = [
    'Id доходного договора/ДС', 'Cid договора/ДС',
    'Номер доходного договора/ДС', 'Дата доходного договора/ДС',
    'Дата окончания срока действия договора', 'Тип',
    'ИНН заказчика', 'Заказчик', 'Номер основного договора',
    'Агент действует', 'Статус', 'Дата статуса', 'Текст ошибок',
]
FINAL_ROW = [
    'CTtest0000000000000002BB', '22222222-3333-4444-5555-666666666666',
    TEST_CONTRACT_NUMBER, '05.02.2025', '', 'Договор оказания услуг',
    TEST_CONTRACT_INN, 'ООО «Тестовый заказчик»', '',
    '', 'Зарегистрирован', '17.06.2025 13:48', '',
]


def _purge_ord_test_rows(db):
    """Снести все CTtest*-строки, договор-заглушку и фиктивных контрагентов.

    Вызывается и до, и после теста: до — на случай что прошлый прогон упал раньше
    своего собственного cleanup и оставил мусор, который иначе тихо накапливался бы.
    """
    db.rollback()
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
    # Контракты-заглушки на C1: не только TEST_CONTRACT_INN, но и любой номер этого
    # файла (несколько тестов ниже заводят по два договора с одинаковым свёрнутым
    # номером и своими, отдельными фиктивными ИНН — см. test_two_candidates_*).
    db.query(Contract).filter(
        (Contract.inn == TEST_CONTRACT_INN) |
        (Contract.contract_number.like(f'{TEST_ORD_PREFIX}%'))
    ).delete(synchronize_session=False)
    db.query(Counterparty).filter(Counterparty.inn.in_(TEST_INNS)).delete(synchronize_session=False)
    # Зеркало доходных — ещё одно место, куда пишет загрузка с 21.09.2026. Уборка о нём
    # узнала не сама: четыре тестовые строки успели осесть на стенде, пока фикстура
    # чистила только зеркало изначальных.
    db.query(OrdFinalMirror).filter(
        OrdFinalMirror.ord_id.like(f'{TEST_ORD_PREFIX}%')
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def db():
    """Настоящая сессия (app.database.SessionLocal) на рабочей базе.

    TEST_INNS обязаны не совпадать ни с одним реальным контрагентом — иначе upsert()
    сопоставил бы чужую строку как «контрагент встретился в выгрузке» (шаг 1 внутри
    upsert считает совпадения Counterparty.inn с ИНН из выгрузки). Проверено запросом
    к боевой базе перед тем, как эти тесты писались; assert ниже — чтобы при
    расхождении тест падал громко, а не молча портил данные.

    Находка ревью I6: проверка обязана идти ДО очистки, не после. Порядок «сначала
    почистить, потом проверить» гарантированно не находит клэша, даже если он был, —
    к моменту assert-а страховка уже снесла всё, включая настоящего контрагента,
    который просто оказался тёзкой по ИНН: «если бы были заняты — их бы уже
    удалили». Проверка идёт на состоянии базы ДО очистки; цена за то, что она вообще
    что-то ловит, — мусор от собственного упавшего прогона этого файла тоже уронит
    assert (тест когда-то создал строку с этим ИНН и не успел её убрать) и потребует
    разовой ручной уборки, а не тихо самоисцелится следующим запуском.
    """
    session = SessionLocal()
    clash = session.query(Counterparty.inn).filter(Counterparty.inn.in_(TEST_INNS)).all()
    assert not clash, (
        f"фиктивные ИНН {TEST_INNS} заняты реальными контрагентами {clash} — "
        f"тест на upsert() их бы пометил; возьми другую фиктивную серию"
    )
    _purge_ord_test_rows(session)
    try:
        yield session
    finally:
        _purge_ord_test_rows(session)
        session.close()


def test_upsert_is_idempotent_second_run_updates_not_duplicates(db):
    """Повторный прогон того же файла обновляет строку, а не плодит вторую.

    Без этого теста регрессия здесь не была бы поймана ни разу — ни один из семи
    тестов выше не вызывает upsert().
    """
    data = _book('Изначальные договоры', INITIAL_HEADER, [INITIAL_ROW])

    stat1 = importer.upsert(db, initial=data)
    assert stat1['initial'] == 1
    assert stat1['links'] == 1

    row = (db.query(OrdInitialContract)
             .filter(OrdInitialContract.ord_id == 'CTtest0000000000000001AA')
             .one())
    assert db.query(OrdInitialFinalLink).filter(
        OrdInitialFinalLink.initial_contract_id == row.id).count() == 1

    stat2 = importer.upsert(db, initial=data)
    assert stat2['initial'] == 0, "повторный прогон завёл вторую строку вместо обновления"
    assert stat2['links'] == 0, "повторный прогон завёл вторую связь вместо обновления"

    assert db.query(OrdInitialContract).filter(
        OrdInitialContract.ord_id == 'CTtest0000000000000001AA').count() == 1
    assert db.query(OrdInitialFinalLink).filter(
        OrdInitialFinalLink.initial_contract_id == row.id).count() == 1


def test_upsert_collapses_repeated_initial_rows_into_one_contract_many_links(db):
    """Несколько строк выгрузки с одним Id изначального договора дают ОДИН
    OrdInitialContract и НЕСКОЛЬКО OrdInitialFinalLink — ради этого и менялась схема
    (в боевой выгрузке 152 строки -> 126 договоров, 150 связей).
    """
    row_a = list(INITIAL_ROW)
    row_b = list(INITIAL_ROW)
    row_b[28] = 'CTtest0000000000000003CC'      # другой Id доходного договора
    row_b[29] = 'ТД-02/2025'
    data = _book('Изначальные договоры', INITIAL_HEADER, [row_a, row_b])

    stat = importer.upsert(db, initial=data)
    assert stat['initial'] == 1
    assert stat['links'] == 2

    row = (db.query(OrdInitialContract)
             .filter(OrdInitialContract.ord_id == 'CTtest0000000000000001AA')
             .one())
    links = (db.query(OrdInitialFinalLink)
               .filter(OrdInitialFinalLink.initial_contract_id == row.id)
               .all())
    assert {ln.final_ord_id for ln in links} == {
        'CTtest0000000000000002BB', 'CTtest0000000000000003CC',
    }


def test_upsert_orders_final_before_initial_so_the_link_finds_the_contract(db):
    """Доходные размечаются раньше изначальных — иначе связь находит наш договор
    только со второго прогона (см. докстринг upsert()). Регрессия на переупорядочивание
    двух циклов внутри функции.

    Заглушке нужен contract_number, совпадающий с TEST_CONTRACT_NUMBER: кандидат тут
    ровно один, и _match_contract возвращает его по одному номеру, даже не заглядывая
    в ИНН (тот проверяется, только если кандидатов несколько — см.
    test_two_candidates_same_folded_number_resolved_by_matching_inn ниже).
    """
    assert db.query(Contract).filter(Contract.inn == TEST_CONTRACT_INN).count() == 0, (
        "тестовый ИНН неожиданно занят реальным договором — возьми другой"
    )
    stub = Contract(inn=TEST_CONTRACT_INN, contract_number=TEST_CONTRACT_NUMBER)
    db.add(stub)
    db.flush()   # autoflush выключен (SessionLocal) — _match_contract должен увидеть строку

    initial_data = _book('Изначальные договоры', INITIAL_HEADER, [INITIAL_ROW])
    final_data = _book('Доходные договоры', FINAL_HEADER, [FINAL_ROW])

    importer.upsert(db, initial=initial_data, final=final_data)

    db.refresh(stub)
    assert stub.ord_contract_id == 'CTtest0000000000000002BB'
    assert stub.ord_kind == 'final'

    link = (db.query(OrdInitialFinalLink)
              .filter(OrdInitialFinalLink.final_ord_id == 'CTtest0000000000000002BB')
              .one())
    assert link.contract_id == stub.id, (
        "связь не нашла только что помеченный договор — доходные обработались позже изначальных"
    )


def test_unmatched_number_is_not_guessed_from_the_only_contract_at_counterparty(db):
    """Решение владельца 2026-08-25: система не подбирает договор по ИНН контрагента,
    даже если он у него единственный без ord_contract_id — это была догадка, а не
    найденное соответствие (11 из 48 меток на боевых данных держались только на ней).
    Совпадать обязан номер; не найденное — в warnings, связь расставляет человек через
    форму сборки. Регрессия именно на возврат убранной ветки в _match_contract.
    """
    assert db.query(Contract).filter(Contract.inn == TEST_CONTRACT_INN).count() == 0, (
        "тестовый ИНН неожиданно занят реальным договором — возьми другой"
    )
    # Тот же ИНН, что и в ОРД-строке (TEST_CONTRACT_INN, единственный договор
    # контрагента), но номер заведомо другой — старый фолбэк угадал бы этот договор.
    stub = Contract(inn=TEST_CONTRACT_INN, contract_number='СОВСЕМ-ДРУГОЙ-НОМЕР/2024')
    db.add(stub)
    db.flush()

    final_data = _book('Доходные договоры', FINAL_HEADER, [FINAL_ROW])
    stat = importer.upsert(db, final=final_data)

    db.refresh(stub)
    assert stub.ord_contract_id is None, (
        "договор помечен по единственности у контрагента — это и есть убранная догадка"
    )
    assert stub.ord_kind is None
    assert stat['contracts'] == 0

    matched_warnings = [w for w in stat['warnings'] if 'CTtest0000000000000002BB' in w]
    assert len(matched_warnings) == 1
    # Формулировка изменилась 21.09.2026 вместе с появлением зеркала доходных: та же
    # фраза стала причиной, которая ХРАНИТСЯ в ord_final_mirror.match_note, а не только
    # звучит в отчёте. Проверяем смысл — «такого договора у нас нет», — а не буквы.
    assert 'нет в нашем реестре' in matched_warnings[0]


# ── _match_contract(): неоднозначность по номеру — находка ревью C1, 25.08.2026 ─
#
# До фикса _match_contract брал первого попавшегося кандидата, совпавшего по
# свёрнутому номеру, не проверяя, что он единственный. На боевых данных — шесть пар
# договоров с одинаковым свёрнутым номером (в четырёх — разные контрагенты), и для
# одной пары метка доказуемо ушла не на тот договор. Два теста ниже — тот же приём,
# что test_unmatched_number_is_not_guessed_from_the_only_contract_at_counterparty
# выше (регрессия на возврат убранной догадки), для новой неоднозначности.

TEST_TWO_CANDIDATE_INNS = ('7700000010', '7700000011', '7700000012', '7700000013')


def test_two_candidates_same_folded_number_neither_tagged_without_inn_match(db):
    """Два наших договора с одинаковым свёрнутым номером, и ИНН заказчика из строки
    ОРД не совпадает ни с одним из них — неоднозначность не разрешена. Система не
    метит первого попавшегося (старое поведение до C1), а не метит НИ ОДНОГО и
    оставляет предупреждение с обоими кандидатами: решение владельца — не подбирать
    соответствие самой, а показывать только то, что совпало буквально.
    """
    stub_a = Contract(inn=TEST_TWO_CANDIDATE_INNS[0],
                      contract_number=f'{TEST_ORD_PREFIX}-СПОР/2026')
    stub_b = Contract(inn=TEST_TWO_CANDIDATE_INNS[1],
                      contract_number=f'{TEST_ORD_PREFIX}-СПОР/2026')
    db.add_all([stub_a, stub_b])
    db.flush()

    row = list(FINAL_ROW)
    row[0] = f'{TEST_ORD_PREFIX}0000000000000004DD'
    row[2] = f'{TEST_ORD_PREFIX}-СПОР/2026'
    row[6] = '7700000098'   # ИНН заказчика — ни с одним из двух кандидатов не совпадает
    final_data = _book('Доходные договоры', FINAL_HEADER, [row])

    stat = importer.upsert(db, final=final_data)

    db.refresh(stub_a)
    db.refresh(stub_b)
    assert stub_a.ord_contract_id is None, (
        "помечен первый попавшийся кандидат — неоднозначность разрешена молча"
    )
    assert stub_b.ord_contract_id is None
    assert stat['contracts'] == 0

    amb = [w for w in stat['warnings'] if f'{TEST_ORD_PREFIX}0000000000000004DD' in w]
    assert len(amb) == 1, f"нет ровно одного предупреждения о неоднозначности: {stat['warnings']}"
    assert 'несколько' in amb[0].lower()
    assert str(stub_a.id) in amb[0] and str(stub_b.id) in amb[0], (
        f"предупреждение не называет обоих кандидатов: {amb[0]}"
    )


def test_two_candidates_same_folded_number_resolved_by_matching_inn(db):
    """Та же неоднозначность по номеру, но ИНН заказчика из строки ОРД совпадает
    ровно с одним из двух кандидатов — точное совпадение по двум независимым
    признакам (номер + ИНН), не догадка. Ровно так на боевых данных разошлась
    находка C1: у одного договора ИНН находился в выгрузке, у другого — нет.
    """
    stub_match = Contract(inn=TEST_TWO_CANDIDATE_INNS[2],
                          contract_number=f'{TEST_ORD_PREFIX}-СПОР2/2026')
    stub_other = Contract(inn=TEST_TWO_CANDIDATE_INNS[3],
                          contract_number=f'{TEST_ORD_PREFIX}-СПОР2/2026')
    db.add_all([stub_match, stub_other])
    db.flush()

    row = list(FINAL_ROW)
    row[0] = f'{TEST_ORD_PREFIX}0000000000000005EE'
    row[2] = f'{TEST_ORD_PREFIX}-СПОР2/2026'
    row[6] = TEST_TWO_CANDIDATE_INNS[2]   # совпадает только с stub_match
    final_data = _book('Доходные договоры', FINAL_HEADER, [row])

    stat = importer.upsert(db, final=final_data)

    db.refresh(stub_match)
    db.refresh(stub_other)
    assert stub_match.ord_contract_id == f'{TEST_ORD_PREFIX}0000000000000005EE', (
        "не помечен единственный кандидат, точно совпавший по ИНН"
    )
    assert stub_other.ord_contract_id is None
    assert stat['contracts'] == 1


# ── read_*: прочитанные строки отдельно от заведённых — находка ревью I1 ───────

def test_read_count_is_reported_even_when_nothing_is_recognized(db):
    """Лист с непустой строкой, но без единого распознанного идентификатора — до
    находки I1 это выглядело ТОЧНО как обычная повторная загрузка: «заведено 0» и
    ни одного предупреждения что там, что там. read_final обязан остаться больше
    нуля, и должно появиться предупреждение — приложен не тот файл, или кабинет
    переименовал колонку.
    """
    row = list(FINAL_ROW)
    row[0] = ''   # Id доходного договора/ДС пуст — вся строка пропускается parse_final
    data = _book('Доходные договоры', FINAL_HEADER, [row])

    stat = importer.upsert(db, final=data)

    assert stat['read_final'] == 1, "в листе одна строка данных — должно быть прочитано 1"
    assert stat['contracts'] == 0
    assert any('Доходные договоры' in w and 'идентификатор' in w for w in stat['warnings']), (
        f"строка прочитана, распознавать было нечего, а предупреждения нет: {stat['warnings']}"
    )


def test_read_count_matches_created_and_stays_quiet_on_a_normal_run(db):
    """Обычный успешный прогон — read_final и «заведено» совпадают, никакого
    предупреждения про нераспознанные строки быть не должно."""
    stub = Contract(inn=TEST_CONTRACT_INN, contract_number=TEST_CONTRACT_NUMBER)
    db.add(stub)
    db.flush()
    data = _book('Доходные договоры', FINAL_HEADER, [FINAL_ROW])

    stat = importer.upsert(db, final=data)

    assert stat['read_final'] == 1
    assert stat['contracts'] == 1
    assert not any('идентификатор' in w for w in stat['warnings'])


# ── ord_client_id: колонка не пишется, clients считает совпадения — находка I2 ──

def test_upsert_does_not_write_surrogate_and_counts_matched_by_inn(db):
    """В выгрузке кабинета настоящего id юрлица нет — писать в ord_client_id
    суррогат 'xlsx:<ИНН>' значит навсегда занять колонку, предназначенную для
    настоящего id ОРД (этап 2, API), под условием «если пусто». Колонка обязана
    остаться пустой; факт «контрагент встретился в выгрузке» несёт stat['clients'],
    а не запись в базе.
    """
    cp = Counterparty(name=f'{TEST_ORD_PREFIX} Контрагент Из Выгрузки', inn=TEST_INNS[0])
    db.add(cp)
    db.flush()

    row = list(FINAL_ROW)
    row[6] = TEST_INNS[0]   # ИНН заказчика совпадает с только что заведённым контрагентом
    data = _book('Доходные договоры', FINAL_HEADER, [row])

    stat = importer.upsert(db, final=data)

    db.refresh(cp)
    assert cp.ord_client_id is None, "в колонку снова записан суррогат"
    assert stat['clients'] == 1
