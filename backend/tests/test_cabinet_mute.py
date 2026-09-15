# -*- coding: utf-8 -*-
"""Выключатели уведомлений паблишера: словарь, запись через ядро, необязательный вид.

Профиль рассылки паблишера задан нами — площадка не собирает подписку, а выключает
лишнее. Отсюда форма хранения: строка есть = выключено, строки нет = включено. Новый вид
включается сам и не требует бэкфилла всем учёткам.

Проверяется то, что ломается молча: опечатка в ключе вида (переключатель нарисуется и
ничего не выключит), запись мимо ядра (у таблицы обязан быть один писатель) и снятие
запрета с вида, который выключать нельзя.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.notify.outward.kinds import KIND_KEYS, KINDS, MUTABLE_KEYS
from app.database import SessionLocal
from app.routers import cabinet_gateway as gw


@pytest.fixture
def acc():
    """Учётка с видимой ей площадкой. Отметки снимаются до и после — следов не остаётся.

    Площадка берётся ОТ КАБИНЕТА, а не из `cabinet_account_publisher`: личный список
    заморожен 30.08.2026, и стенд, построенный на нём, проверял бы правило, которого
    больше нет.
    """
    from app.cabinet.models import CabinetAccount
    from app.cabinet.scope import visible_publisher_ids

    db = SessionLocal()
    row = None
    for a in (db.query(CabinetAccount).order_by(CabinetAccount.id).all()):
        cab = db.execute(text("SELECT id, kind, state FROM cabinet WHERE id = :c"),
                         {"c": a.cabinet_id}).first() if a.cabinet_id else None
        if cab is None or cab.state != 'активен':
            continue
        ids = visible_publisher_ids(db, type('C', (), dict(id=cab.id, kind=cab.kind)))
        pub = (db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 1")).scalar()
               if ids is None else (min(ids) if ids else None))
        if pub:
            row = type('R', (), dict(id=a.id, publisher_id=pub))
            break
    if row is None:
        db.close()
        pytest.skip('на стенде нет учётки с видимой площадкой')
    db.execute(text("DELETE FROM cabinet_account_mute WHERE account_id = :a"),
               {"a": row.id})
    db.commit()
    yield type('A', (), {'db': db, 'id': row.id, 'pub': row.publisher_id})
    db.execute(text("DELETE FROM cabinet_account_mute WHERE account_id = :a"),
               {"a": row.id})
    # С 05.09.2026 выключатель пишет строку в ленту кабинета. Без уборки каждый прогон
    # тестов оставлял бы площадке пару строк «уведомление выключено/возвращено» — ленту
    # читает внешний человек, и наш прогон в ней выглядел бы её собственным действием.
    db.execute(text("DELETE FROM cabinet_log WHERE account_id = :a "
                    "AND action IN ('уведомление_выкл', 'уведомление_вкл')"),
               {"a": row.id})
    db.commit()
    db.close()


def _muted(db, account_id):
    return {k for (k,) in db.execute(
        text("SELECT kind FROM cabinet_account_mute WHERE account_id = :a"),
        {"a": account_id}).all()}


def test_default_is_everything_on(acc):
    """Отсутствие строк означает «всё включено», а не «ничего не настроено».

    На этом стоит вся форма хранения: если однажды прочитать пустоту как «выключено»,
    площадка перестанет получать всё разом и не поймёт почему.
    """
    assert _muted(acc.db, acc.id) == set()


def test_mute_and_unmute_are_symmetric(acc):
    gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind='сверка',
                                             muted=True, author_name='тест'), acc.db)
    assert 'сверка' in _muted(acc.db, acc.id)
    gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind='сверка',
                                             muted=False), acc.db)
    assert 'сверка' not in _muted(acc.db, acc.id)


def test_muting_twice_does_not_duplicate(acc):
    """Повторное выключение не плодит строк — первичный ключ по паре."""
    for _ in range(3):
        gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind='продление',
                                                 muted=True), acc.db)
    n = acc.db.execute(text(
        "SELECT count(*) FROM cabinet_account_mute WHERE account_id = :a AND kind = 'продление'"),
        {"a": acc.id}).scalar()
    assert n == 1


def test_unknown_kind_is_refused(acc):
    """Опечатка в ключе не должна создавать строку.

    Внешнего ключа на справочник нет намеренно — он живёт в коде. Значит проверку несёт
    ручка, и без этого прибора опечатка тихо выключила бы несуществующий вид, а
    настоящий продолжал бы приходить.
    """
    with pytest.raises(HTTPException) as e:
        gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind='сверкa',
                                                 muted=True), acc.db)
    assert e.value.status_code == 400
    assert _muted(acc.db, acc.id) == set()


def test_mandatory_kind_cannot_be_muted(acc):
    """«Старт близко» выключить нельзя: пропущенное здесь стоит сорванного запуска."""
    hard = [k.key for k in KINDS if not k.can_mute]
    assert hard, 'ни одного обязательного вида — исключение потерялось'
    with pytest.raises(HTTPException) as e:
        gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind=hard[0],
                                                 muted=True), acc.db)
    assert e.value.status_code == 400


def test_publisher_of_another_cabinet_is_404():
    """Чужая площадка отвечает 404, а не 403.

    403 подтвердил бы, что связка существует, — и перебор номеров превратился бы в
    способ узнать, кто с кем работает.

    Стенд строится СВОЙ, а не берётся готовый, и это не прихоть: единственная учётка
    стенда сидит в служебном кабинете, а он видит все площадки — чужой для неё не бывает
    вовсе, и прибор был бы зелёным всегда. Прежняя редакция как раз этим и болела: она
    искала площадку вне личного списка, а после заморозки списка правило стало другим.
    """
    from app.cabinet.models import Cabinet, CabinetAccount, CabinetPublisher

    db = SessionLocal()
    free = [i for (i,) in db.execute(text(
        "SELECT p.id FROM sales_publishers p WHERE NOT EXISTS ("
        "  SELECT 1 FROM cabinet_publisher cp WHERE cp.publisher_id = p.id)"
        " ORDER BY p.id LIMIT 2")).all()]
    if len(free) < 2:
        db.close()
        pytest.skip('нужны две площадки вне кабинетов')

    cab = Cabinet(name='__тест области__', kind='площадка', state='активен')
    db.add(cab)
    db.flush()
    a = CabinetAccount(email='scope-probe@lk.local', name='Проба области',
                       cabinet_id=cab.id)
    db.add(a)
    db.add(CabinetPublisher(cabinet_id=cab.id, publisher_id=free[0]))
    db.commit()
    try:
        # Своя — проходит.
        gw.cabinet_mute(a.id, gw.CabinetMuteIn(publisher_id=free[0], kind='сверка',
                                               muted=True), db)
        # Чужая и несуществующая — одинаково 404, чтобы по коду ответа нельзя было
        # отличить «есть, но не твоя» от «нет такой».
        for pid in (free[1], 10 ** 9):
            with pytest.raises(HTTPException) as e:
                gw.cabinet_mute(a.id, gw.CabinetMuteIn(publisher_id=pid, kind='сверка',
                                                       muted=True), db)
            assert e.value.status_code == 404
    finally:
        db.rollback()
        db.execute(text("DELETE FROM cabinet_account_mute WHERE account_id = :a"),
                   {"a": a.id})
        db.execute(text("DELETE FROM cabinet_account WHERE id = :a"), {"a": a.id})
        db.execute(text("DELETE FROM cabinet_publisher WHERE cabinet_id = :c"),
                   {"c": cab.id})
        db.execute(text("DELETE FROM cabinet WHERE id = :c"), {"c": cab.id})
        db.commit()
        db.close()


def test_suspended_cabinet_cannot_write():
    """Приостановленный кабинет не может и писать, а не только смотреть.

    Приостановка означает «люди кабинета сразу перестают видеть задания». Проверка
    записи, не знающая о состоянии, оставила бы им возможность отвечать по тому, что уже
    не показывается, — и вердикт пришёл бы из кабинета, который для нас выключен.
    """
    from app.cabinet.models import Cabinet, CabinetAccount, CabinetPublisher

    db = SessionLocal()
    free = db.execute(text(
        "SELECT p.id FROM sales_publishers p WHERE NOT EXISTS ("
        "  SELECT 1 FROM cabinet_publisher cp WHERE cp.publisher_id = p.id)"
        " ORDER BY p.id LIMIT 1")).scalar()
    if not free:
        db.close()
        pytest.skip('нужна площадка вне кабинетов')

    cab = Cabinet(name='__тест паузы__', kind='площадка', state='приостановлен')
    db.add(cab)
    db.flush()
    a = CabinetAccount(email='pause-probe@lk.local', name='Проба паузы', cabinet_id=cab.id)
    db.add(a)
    db.add(CabinetPublisher(cabinet_id=cab.id, publisher_id=free))
    db.commit()
    try:
        with pytest.raises(HTTPException) as e:
            gw.cabinet_mute(a.id, gw.CabinetMuteIn(publisher_id=free, kind='сверка',
                                                   muted=True), db)
        assert e.value.status_code == 404
    finally:
        db.rollback()
        db.execute(text("DELETE FROM cabinet_account_mute WHERE account_id = :a"),
                   {"a": a.id})
        db.execute(text("DELETE FROM cabinet_account WHERE id = :a"), {"a": a.id})
        db.execute(text("DELETE FROM cabinet_publisher WHERE cabinet_id = :c"),
                   {"c": cab.id})
        db.execute(text("DELETE FROM cabinet WHERE id = :c"), {"c": cab.id})
        db.commit()
        db.close()


def test_vocabulary_is_coherent():
    """Справочник не расходится сам с собой."""
    assert len(set(KIND_KEYS)) == len(KIND_KEYS), 'дубли ключей'
    assert set(MUTABLE_KEYS) <= set(KIND_KEYS)
    assert len(MUTABLE_KEYS) < len(KIND_KEYS), (
        'выключить можно всё — обязательный вид потерялся'
    )


def test_switch_leaves_a_trace_in_the_cabinet_feed(acc):
    """Выключатель пишет в ленту кабинета — обе стороны видят, когда состояние сменили.

    Сама строка `cabinet_account_mute` помнит ТЕКУЩЕЕ состояние и не помнит, когда его
    сменили и кто. Разговор «мы вам писали» / «нам не приходило» упирался в то, что
    записи нет ни у кого. Событий два, а не одно с флагом: в ленте читают глаголы, и
    «выключено» обязано отличаться тоном от «возвращено».
    """
    from app.notify.outward.kinds import KINDS, MUTABLE_KEYS
    from app.routers import cabinet_gateway as gw

    kind = sorted(MUTABLE_KEYS)[0]
    label = next(k.label for k in KINDS if k.key == kind)
    before = _feed(acc.db, acc.id)

    gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind=kind,
                                             muted=True, author_name='Прибор'), acc.db)
    gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=acc.pub, kind=kind,
                                             muted=False, author_name='Прибор'), acc.db)

    rows = _feed(acc.db, acc.id)[len(before):]
    assert [r.action for r in rows] == ['уведомление_выкл', 'уведомление_вкл']
    # В ленту едет ЧЕЛОВЕЧЕСКОЕ имя вида, а не ключ: её читает и площадка тоже.
    assert all(r.subject == label for r in rows), [r.subject for r in rows]
    assert all(r.actor_side == 'площадка' for r in rows)
    assert [r.tone for r in rows] == ['warn', 'ok']


def _feed(db, account_id):
    from app.cabinet.models import CabinetLog
    return (db.query(CabinetLog)
            .filter(CabinetLog.account_id == account_id,
                    CabinetLog.action.in_(['уведомление_выкл', 'уведомление_вкл']))
            .order_by(CabinetLog.id).all())
