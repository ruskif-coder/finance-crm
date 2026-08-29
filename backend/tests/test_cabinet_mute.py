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

from app.cabinet.notify_kinds import KIND_KEYS, KINDS, MUTABLE_KEYS
from app.database import SessionLocal
from app.routers import cabinet_gateway as gw


@pytest.fixture
def acc():
    """Учётка с площадкой. Отметки снимаются до и после — тест не оставляет следов."""
    db = SessionLocal()
    row = db.execute(text(
        "SELECT a.id, ap.publisher_id FROM cabinet_account a "
        "JOIN cabinet_account_publisher ap ON ap.account_id = a.id LIMIT 1")).first()
    if row is None:
        db.close()
        pytest.skip('на стенде нет учётки с площадкой')
    db.execute(text("DELETE FROM cabinet_account_mute WHERE account_id = :a"),
               {"a": row.id})
    db.commit()
    yield type('A', (), {'db': db, 'id': row.id, 'pub': row.publisher_id})
    db.execute(text("DELETE FROM cabinet_account_mute WHERE account_id = :a"),
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


def test_unlinked_publisher_is_404(acc):
    """Площадка, не связанная с учёткой, отвечает 404, а не 403.

    403 подтвердил бы, что связка существует, — и перебор номеров превратился бы в
    способ узнать, кто с кем работает.

    Берётся площадка ВНЕ списка учётки, а если таких нет — заведомо несуществующий
    номер. Первая версия теста брала «любую другую» и не падала: тестовая учётка связана
    со всеми 41 площадкой стенда, то есть чужой для неё просто не бывает.
    """
    other = acc.db.execute(text(
        "SELECT p.id FROM sales_publishers p WHERE NOT EXISTS ("
        "  SELECT 1 FROM cabinet_account_publisher ap"
        "   WHERE ap.account_id = :a AND ap.publisher_id = p.id) ORDER BY p.id LIMIT 1"),
        {"a": acc.id}).scalar() or 10 ** 9
    with pytest.raises(HTTPException) as e:
        gw.cabinet_mute(acc.id, gw.CabinetMuteIn(publisher_id=other, kind='сверка',
                                                 muted=True), acc.db)
    assert e.value.status_code == 404


def test_vocabulary_is_coherent():
    """Справочник не расходится сам с собой."""
    assert len(set(KIND_KEYS)) == len(KIND_KEYS), 'дубли ключей'
    assert set(MUTABLE_KEYS) <= set(KIND_KEYS)
    assert len(MUTABLE_KEYS) < len(KIND_KEYS), (
        'выключить можно всё — обязательный вид потерялся'
    )
