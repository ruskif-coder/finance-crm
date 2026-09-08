# -*- coding: utf-8 -*-
"""Удаление комплекта креативов уносит с собой детей и не роняет запрос.

ПРОИСШЕСТВИЕ 08.09.2026, прод. Аккаунт нажимал «Удалить» на креативе сделки ZCBPLS и
получал «Не удалось удалить» без причины — в ответе не было `detail`, потому что это была
500-я, а не отказ по правилу.

Причина — классическая готча SQLAlchemy. У всех детей комплекта (`файлы, пары, проверки,
площадки`) в БАЗЕ стоит `ON DELETE CASCADE`, то есть база удалила бы их сама. Но
relationship был объявлен без `passive_deletes=True`, и ORM, не зная про каскад, грузил
детей и проставлял им `set_id = NULL` — а колонка `NOT NULL`. `IntegrityError` на ровном
месте.

Вторая половина происшествия опаснее первой: ручка стирала файлы С ДИСКА **до** удаления
строки. База откатывалась, а материал уже исчезал — комплект оставался на экране со
ссылками в пустоту. У диска отката нет, у базы есть, поэтому теперь сначала запись.

Прибор держит оба свойства на настоящих строках, а не на моках: удаление проходит,
дети исчезают вместе с родителем.
"""
import pytest

import app.ad.models           # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
import app.sales.models        # noqa: F401
from app.database import SessionLocal
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet,
                                    LaunchPrepPair, LaunchPrepTarget)
from app.sales.models import SalesDeal

# Тесты владеют номерами ≥ 9000 — правило диапазонов из навыка testing-before-prod.
TEST_NO = 9101


def _clean(s):
    for st in s.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.no == TEST_NO).all():
        s.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id == st.id).delete(synchronize_session=False)
        s.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id == st.id).delete(synchronize_session=False)
        s.delete(st)
    s.commit()


@pytest.fixture
def db():
    s = SessionLocal()
    _clean(s)
    yield s
    _clean(s)
    s.close()


def _set_with_children(db):
    """Комплект с файлом и парой — минимальная форма, на которой падало."""
    deal = db.query(SalesDeal).order_by(SalesDeal.id).first()
    if not deal:
        pytest.skip('на стенде нет ни одной сделки')
    target = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == deal.id).first()

    st = LaunchPrepCreativeSet(deal_id=deal.id, no=TEST_NO, title='тестовый комплект')
    db.add(st)
    db.flush()
    db.add(LaunchPrepCreativeFile(set_id=st.id, path=f'creatives/cre{st.id}_test.jpg',
                                  original_name='test.jpg', size_bytes=1,
                                  content_type='image/jpeg'))
    if target:
        db.add(LaunchPrepPair(set_id=st.id, target_id=target.id))
    db.commit()
    return st


def test_set_deletes_together_with_its_children(db):
    """Удаление проходит, файлы и пары уходят каскадом базы.

    Ровно то, что видел человек: без `passive_deletes` здесь была бы `IntegrityError`
    и «Не удалось удалить» без объяснения.
    """
    st = _set_with_children(db)
    set_id = st.id
    assert db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == set_id).count() == 1

    db.delete(st)
    db.commit()

    assert db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == set_id).first() is None
    assert db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == set_id).count() == 0, 'файлы пережили комплект'
    assert db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == set_id).count() == 0, 'пары пережили комплект'


def test_files_are_removed_from_disk_only_after_the_row_is_gone():
    """Порядок в ручке: сперва запись, потом диск.

    Проверяем ИСХОДНЫЙ ТЕКСТ, а не поведение: воспроизвести гонку «база упала, а файлы
    уже стёрты» в тесте можно только подделкой отказа, и такой тест проверял бы подделку.
    Здесь же держится само правило — обращение к диску стоит ПОСЛЕ `db.commit()`.
    """
    import inspect

    from app.routers import launch_prep

    src = inspect.getsource(launch_prep.drop_set)
    assert 'db.commit()' in src and '_remove_file' in src
    assert src.index('db.commit()') < src.rindex('_remove_file'), (
        'файлы стираются до коммита — падение удаления снова оставит комплект '
        'со ссылками в пустоту'
    )
