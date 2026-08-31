# -*- coding: utf-8 -*-
"""Журнал кабинета: словарь, единственная точка записи и вход.

Ленту читают ДВОЕ — администратор и сама площадка, — поэтому ошибка здесь не «пустая
колонка», а строка, которую внешний человек увидит неверной: не тем цветом, не с той
стороны или без автора.

Главный прибор файла — **у каждого события есть производитель**. Это тот же урок, что с
правилами сканера без подписчиков: пункт словаря, которого никто не пишет, невозможно
отличить от «события не было», и он тихо копится годами. Ищем производителей и в Python,
и в SQL: вход пишет функция `pub.touch_login`, потому что это единственная запись,
которую внешнему контуру разрешено делать в `public`.
"""
import pathlib
import re

import pytest
from sqlalchemy import text

from app.cabinet import journal
from app.cabinet.models import (Cabinet, CabinetAccount, CabinetLog, LOG_SIDES,
                                LOG_TONES)
from app.database import SessionLocal
from app.sales.models import SalesPublisher  # noqa: F401  — см. test_cabinet_scope

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_every_action_has_a_producer():
    """Событие без пишущего кода — это пункт, по которому нельзя отличить «не было» от
    «не записали»."""
    sources = []
    for f in (ROOT / 'app').rglob('*.py'):
        if f.name == 'journal.py':
            continue                      # объявление словаря — не производитель
        sources.append(f.read_text(encoding='utf-8'))
    for f in (ROOT / 'migrations').glob('*.sql'):
        sources.append(f.read_text(encoding='utf-8'))
    blob = '\n'.join(sources)

    orphans = [a.key for a in journal.ACTIONS if f"'{a.key}'" not in blob]
    assert not orphans, (
        'события есть в словаре, но их никто не пишет: ' + ', '.join(orphans))


def test_unknown_action_is_refused():
    """Опечатка в ключе обязана падать, а не заводить строку с выдуманным действием.

    Констрейнта в базе нет намеренно (словари проекта живут в коде), поэтому вся защита
    здесь и состоит из этой проверки.
    """
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            journal.write(db, 'выдуманное', cabinet_id=1, actor_name='тест')
    finally:
        db.rollback()
        db.close()


def test_tone_and_side_come_from_the_dictionary_not_the_caller():
    """Сторона и тон заданы СОБЫТИЕМ. Иначе одно действие однажды придёт в ленту двумя
    разными цветами, и площадка увидит согласование красным."""
    for a in journal.ACTIONS:
        assert a.tone in LOG_TONES, f'{a.key}: неизвестный тон {a.tone!r}'
        assert a.side in LOG_SIDES, f'{a.key}: неизвестная сторона {a.side!r}'
    # Подписи не повторяются: две одинаковые строки в ленте неразличимы для читателя.
    labels = [a.label for a in journal.ACTIONS]
    assert len(set(labels)) == len(labels), 'повторяющиеся подписи событий'
    keys = [a.key for a in journal.ACTIONS]
    assert len(set(keys)) == len(keys), 'дубли ключей'


def test_row_without_cabinet_is_not_written():
    """Учётке без кабинета писать некуда — и это не ошибка, а отсутствие читателя."""
    db = SessionLocal()
    try:
        assert journal.write(db, 'пароль', cabinet_id=None, actor_name='тест') is None
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def stand():
    """Свой кабинет с учёткой: чужой журнал засорять нельзя, его читает площадка."""
    db = SessionLocal()
    cab = Cabinet(name='__журнал__', kind='площадка', state='активен')
    db.add(cab)
    db.flush()
    acc = CabinetAccount(email='journal-probe@lk.local', name='Проба журнала',
                         cabinet_id=cab.id)
    db.add(acc)
    db.commit()
    yield type('S', (), dict(db=db, cab=cab.id, acc=acc.id))
    db.rollback()
    db.execute(text("DELETE FROM cabinet_log WHERE cabinet_id = :c"), {"c": cab.id})
    db.execute(text("DELETE FROM cabinet_account WHERE id = :a"), {"a": acc.id})
    db.execute(text("DELETE FROM cabinet WHERE id = :c"), {"c": cab.id})
    db.commit()
    db.close()


def test_written_row_carries_side_and_tone_of_its_action(stand):
    db = stand.db
    journal.write(db, 'уровень', cabinet_id=stand.cab, account_id=stand.acc,
                  actor_name='Дарья Г.', subject='Проба журнала → просмотр')
    db.commit()
    row = (db.query(CabinetLog).filter(CabinetLog.cabinet_id == stand.cab)
           .order_by(CabinetLog.id.desc()).first())
    assert row.action == 'уровень'
    assert row.actor_side == 'мы' and row.tone == 'info'
    assert row.actor_name == 'Дарья Г.'


def test_login_writes_a_row_by_itself(stand):
    """Вход пишет САМА функция ядра, а не отдельный вызов из кабинета.

    Второй канал записи наружу ради одной строки расширил бы поверхность внешнего
    контура — у него ровно одна разрешённая запись в `public`, и это она.
    """
    db = stand.db
    before = db.query(CabinetLog).filter(CabinetLog.cabinet_id == stand.cab).count()
    db.execute(text("SELECT pub.touch_login(:i)"), {"i": stand.acc})
    db.commit()

    rows = (db.query(CabinetLog).filter(CabinetLog.cabinet_id == stand.cab)
            .order_by(CabinetLog.id.desc()).all())
    assert len(rows) == before + 1
    assert rows[0].action == 'вход' and rows[0].actor_side == 'площадка'
    assert rows[0].account_id == stand.acc
    # И отметка времени — та же транзакция, иначе «последний вход» и лента разойдутся.
    assert db.query(CabinetAccount).filter(
        CabinetAccount.id == stand.acc).first().last_login_at is not None


def test_subject_of_our_actions_names_the_person_not_the_deal():
    """Правило «в subject не попадает лишнее» — читаемое, поэтому проверяется грепом.

    Лента у площадки на виду; наши внутренние обозначения (код сделки, ИНН, суммы) в
    ней быть не должны. Прибор ловит самое частое: подстановку кода сделки.
    """
    bad = []
    for f in (ROOT / 'app').rglob('*.py'):
        txt = f.read_text(encoding='utf-8')
        for m in re.finditer(r'journal\.write\((.{0,400}?)\)\n', txt, re.S):
            call = m.group(1)
            if 'subject=' in call and ('deal.code' in call or 'deal_id' in call):
                bad.append(f.name)
    assert not bad, ('в строку журнала подставляется наша внутренняя единица: '
                     + ', '.join(sorted(set(bad))))
