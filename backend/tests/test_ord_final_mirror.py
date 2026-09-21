"""Зеркало доходных договоров ОРД: сопоставление с реестром и разбор несовпавших.

Приборы стоят ровно там, где до 21.09.2026 было тихо:

  · **лист изначальных несёт доходных**, и раньше из них читался только идентификатор.
    Выгрузка владельца от 18.09 состояла из одного этого листа: 41 доходный в файле,
    ноль пометок в системе — и ни одного предупреждения о том, что что-то пропущено;
  · **несовпавший умирал вместе с отчётом** о загрузке. Список «есть в ОРД, нет у нас»
    существовал строкой предупреждения, по которой нельзя разбирать: после следующей
    загрузки он тот же, а отметить «этот разобран» негде;
  · **разбор человека переживает загрузку**. Отложенное с объяснением не должно
    всплывать заново после каждой выгрузки — иначе его перестанут читать.

Эндпоинты зовутся напрямую с фиктивным admin — как в test_launch_prep_directories.py.
"""
from datetime import date
from types import SimpleNamespace

import pytest

import app.notify.models  # noqa: F401  — иначе маппер не найдёт notification_profiles
from app.database import SessionLocal
from app.models import AuditLog, Contract
from app.ord import importer
from app.ord.models import OrdFinalMirror
from app.routers.ord import (FinalDeferIn, FinalLinkIn, defer_final_mirror,
                             link_final_mirror, list_final_mirror)

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None,
                              email='test', name='тест')

ORD_A = 'CTTESTfinalAAAAAAAAAAAAA'      # сойдётся с нашим договором
ORD_B = 'CTTESTfinalBBBBBBBBBBBBB'      # такого договора у нас нет
NUM_A = 'ТЕСТ-ОРД-01'
OUR_NUMBERS = (NUM_A,)


def _final(ord_id, number, inn=None, name='ООО «Тест»', status='Зарегистрирован',
           **extra):
    row = {'ord_id': ord_id, 'ord_cid': None, 'number': number, 'date': date(2025, 1, 1),
           'expiration_date': None, 'type': None, 'client_inn': inn, 'client_name': name,
           'parent_number': None, 'is_agent_acting_for_publisher': None,
           'status': status, 'status_at': None, 'error_text': None, 'warnings': []}
    row.update(extra)
    return row


def _purge(db):
    """Ручки коммитят — rollback за собой не убирает. Журнал действий тоже артефакт."""
    ids = [i for (i,) in db.query(OrdFinalMirror.id)
           .filter(OrdFinalMirror.ord_id.in_((ORD_A, ORD_B))).all()]
    if ids:
        (db.query(AuditLog)
           .filter(AuditLog.action.in_(('ord_defer_final', 'ord_reopen_final')),
                   AuditLog.entity_id.in_(ids)).delete(synchronize_session=False))
    (db.query(OrdFinalMirror)
       .filter(OrdFinalMirror.ord_id.in_((ORD_A, ORD_B))).delete(synchronize_session=False))
    ours = db.query(Contract).filter(Contract.contract_number.in_(OUR_NUMBERS)).all()
    for c in ours:
        (db.query(AuditLog)
           .filter(AuditLog.action == 'ord_link_final',
                   AuditLog.entity_id == c.id).delete(synchronize_session=False))
        db.delete(c)
    db.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


@pytest.fixture
def our_contract(db):
    c = Contract(contract_number=NUM_A, counterparty_name='ООО «Тест»', inn='7700000001')
    db.add(c)
    db.commit()
    return c


# ── чтение доходных из листа изначальных ─────────────────────────────────────

def test_finals_are_read_from_the_initial_sheet():
    """Лист изначальных несёт доходного четырьмя колонками, не одной."""
    rows = [{'final_ord_id': ORD_A, 'final_number': NUM_A,
             'final_client_inn': '7700000001', 'final_client_name': 'ООО «Тест»'}]
    out = importer.finals_from_initial(rows)
    assert len(out) == 1
    assert out[0]['ord_id'] == ORD_A
    assert out[0]['number'] == NUM_A
    assert out[0]['client_inn'] == '7700000001'
    assert out[0]['partial'] is True, 'строка из чужого листа обязана быть помечена неполной'


def test_one_final_under_several_initials_is_counted_once():
    """У одного доходного бывает несколько изначальных — строк в листе несколько."""
    rows = [{'final_ord_id': ORD_A, 'final_number': NUM_A, 'final_client_inn': None,
             'final_client_name': None} for _ in range(3)]
    assert len(importer.finals_from_initial(rows)) == 1


# ── зеркало ──────────────────────────────────────────────────────────────────

def test_matched_and_unmatched_land_in_the_mirror(db, our_contract):
    stat = importer.upsert_rows(db, final=[_final(ORD_A, NUM_A, '7700000001'),
                                           _final(ORD_B, 'НЕТ-ТАКОГО-01', '7700000002')])
    assert stat['final_seen'] == 2
    assert stat['final_unmatched'] == 1

    a = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_A).one()
    b = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_B).one()
    assert a.match_note is None, 'сошедшийся не должен нести причину несовпадения'
    assert b.match_note and 'нет в нашем реестре' in b.match_note
    db.refresh(our_contract)
    assert our_contract.ord_contract_id == ORD_A, 'отметка ставится НА ДОГОВОР'


def test_second_run_changes_nothing(db, our_contract):
    rows = [_final(ORD_A, NUM_A, '7700000001'), _final(ORD_B, 'НЕТ-ТАКОГО-01')]
    first = importer.upsert_rows(db, final=rows)
    second = importer.upsert_rows(db, final=rows)
    assert first['contracts'] == 1 and second['contracts'] == 0
    assert second['final_seen'] == 2 and second['final_unmatched'] == 1
    assert db.query(OrdFinalMirror).filter(
        OrdFinalMirror.ord_id.in_((ORD_A, ORD_B))).count() == 2


def test_partial_row_does_not_erase_the_full_one(db):
    """Неполная строка из листа изначальных дозаполняет, но не затирает статус."""
    importer.upsert_rows(db, final=[_final(ORD_B, 'НЕТ-ТАКОГО-01', status='Зарегистрирован')])
    importer.upsert_rows(db, final=[_final(ORD_B, 'НЕТ-ТАКОГО-01', status=None,
                                           partial=True)])
    row = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_B).one()
    assert row.status == 'Зарегистрирован'


def test_deferred_survives_the_next_import(db):
    """Отложенное с объяснением не всплывает заново после каждой выгрузки."""
    importer.upsert_rows(db, final=[_final(ORD_B, 'НЕТ-ТАКОГО-01')])
    row = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_B).one()
    defer_final_mirror(row.id, FinalDeferIn(note='номер в ОРД ошибочный'), db, _FAKE_ADMIN)

    importer.upsert_rows(db, final=[_final(ORD_B, 'НЕТ-ТАКОГО-01')])
    db.refresh(row)
    assert row.review_state == 'deferred'
    assert row.review_note == 'номер в ОРД ошибочный'
    todo_ids = [x['ord_id'] for x in list_final_mirror('todo', db, _FAKE_ADMIN)['items']]
    assert ORD_B not in todo_ids, 'отложенное не должно висеть в списке на разбор'


def test_defer_without_a_reason_is_refused(db):
    from fastapi import HTTPException
    importer.upsert_rows(db, final=[_final(ORD_B, 'НЕТ-ТАКОГО-01')])
    row = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_B).one()
    with pytest.raises(HTTPException) as e:
        defer_final_mirror(row.id, FinalDeferIn(note='   '), db, _FAKE_ADMIN)
    assert e.value.status_code == 400


# ── ручная привязка ──────────────────────────────────────────────────────────

def test_manual_link_marks_the_contract_and_clears_the_reason(db, our_contract):
    importer.upsert_rows(db, final=[_final(ORD_B, 'НЕТ-ТАКОГО-01', '7700000001')])
    row = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_B).one()
    link_final_mirror(row.id, FinalLinkIn(contract_id=our_contract.id), db, _FAKE_ADMIN)

    db.refresh(our_contract)
    db.refresh(row)
    assert our_contract.ord_contract_id == ORD_B
    assert our_contract.ord_kind == 'final'
    assert row.match_note is None and row.review_state == 'linked'


def test_link_refuses_an_identifier_already_used(db, our_contract):
    """Один идентификатор ОРД на двух наших договорах — рассыпавшаяся отчётность."""
    from fastapi import HTTPException
    importer.upsert_rows(db, final=[_final(ORD_A, NUM_A, '7700000001'),
                                    _final(ORD_B, 'НЕТ-ТАКОГО-01')])
    row_b = db.query(OrdFinalMirror).filter(OrdFinalMirror.ord_id == ORD_B).one()
    # our_contract уже помечен ORD_A загрузкой выше
    with pytest.raises(HTTPException) as e:
        link_final_mirror(row_b.id, FinalLinkIn(contract_id=our_contract.id), db, _FAKE_ADMIN)
    assert e.value.status_code == 400


def test_matched_row_names_our_contract_in_the_listing(db, our_contract):
    """Наш договор в ответе — соединением по идентификатору, не второй колонкой."""
    importer.upsert_rows(db, final=[_final(ORD_A, NUM_A, '7700000001')])
    item = next(x for x in list_final_mirror('all', db, _FAKE_ADMIN)['items']
                if x['ord_id'] == ORD_A)
    assert item['contract'] and item['contract']['number'] == NUM_A


# ── контуры ──────────────────────────────────────────────────────────────────

def test_prod_import_finds_a_contract_already_marked_by_demo(db, our_contract):
    """Боевая выгрузка обязана находить договор, помеченный демо-прогоном.

    На проде 21.09.2026 ВСЕ 35 отметок были демовыми. Кандидаты брались только среди
    договоров без отметки — значит боевая загрузка объявила бы «нет у нас» 34 договора
    из 35: боевой и демовский идентификатор одного договора выглядят разными записями,
    а искать наш договор было негде. Прод вытесняет песочницу, песочница прод — нет.
    """
    our_contract.ord_contract_id = 'CTTESTfinalDEMOOOOOOOOOO'
    our_contract.ord_env = 'demo'
    db.commit()

    stat = importer.upsert_rows(db, final=[_final(ORD_A, NUM_A, '7700000001')], env='prod')
    db.refresh(our_contract)
    assert stat['final_unmatched'] == 0, 'боевая выгрузка не нашла договор с демо-отметкой'
    assert our_contract.ord_contract_id == ORD_A
    assert our_contract.ord_env == 'prod', 'контур обязан обновиться вместе с отметкой'


def test_demo_import_does_not_touch_a_prod_marked_contract(db, our_contract):
    """Обратное направление запрещено: пробный прогон не стирает боевую связь с ЕРИР."""
    our_contract.ord_contract_id = 'CTTESTfinalPRODDDDDDDDDD'
    our_contract.ord_env = 'prod'
    db.commit()

    stat = importer.upsert_rows(db, final=[_final(ORD_A, NUM_A, '7700000001')], env='demo')
    db.refresh(our_contract)
    assert our_contract.ord_contract_id == 'CTTESTfinalPRODDDDDDDDDD'
    assert stat['final_unmatched'] == 1, 'такой доходный должен уйти в список на разбор'


def test_contracts_registry_shows_the_ord_mark(db, our_contract):
    """Отметка ОРД видна в реестре договоров.

    Поле только читается: пишут его загрузка выгрузки и ручная привязка. Прибор на то,
    что сериализатор реестра его не потеряет — иначе колонка «ОРД» тихо опустеет, и
    выглядеть это будет как «сопоставление сломалось».
    """
    from app.routers.contracts import _serialize
    importer.upsert_rows(db, final=[_final(ORD_A, NUM_A, '7700000001')], env='prod')
    db.refresh(our_contract)
    out = _serialize(our_contract)
    assert out['ord_contract_id'] == ORD_A
    assert out['ord_kind'] == 'final'
    assert out['ord_env'] == 'prod', 'без контура демовская отметка неотличима от боевой'
