"""Схема модуля креативов: проверяется то, что защищает БАЗА, а не код.

Два правила здесь стоят на ограничениях, и оба легко потерять при следующей миграции —
код при этом продолжит работать, а порча пойдёт молча:

  · **два ОБЩИХ комплекта с одним номером** должны отклоняться. Обычный UNIQUE их
    пропустит: по умолчанию Postgres считает NULL различными, а «общий комплект» — это
    как раз `publisher_id IS NULL`. Спасает `NULLS NOT DISTINCT` (PG 15+);
  · **ссылка на заменяемый комплект** имеет смысл только у доработки. Без CHECK поле со
    временем наберёт «а мы тут похожий брали за основу», и цепочка перестанет означать
    что-либо.

Плюс пины на словари значений: они намеренно НЕ закреплены CHECK'ом в базе (модуль
трафиков добавит свои под-этапы, и расширение не должно требовать миграции) — значит
закрепить их обязан тест, иначе опечатка в русском литерале не ловится ничем.

Тесты идут на живой базе фиктивными строками, как соседние test_ord_*.py.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.launch_prep.models import (ERID_SOURCES, REVIEW_KINDS, REVIEW_SOURCES,
                                    REVIEW_VERDICTS, SET_ORIGINS, TARGET_STATES,
                                    TARGET_STATE_PUBLIC, LaunchPrepCreativeSet)
from tests._launch_prep_cleanup import drop_campaign_creatives

NO_BASE = 9000          # номера комплектов, которых не бывает у живых сделок


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _purge(session):
    session.rollback()
    drop_campaign_creatives(session, NO_BASE)   # до комплектов: FK без каскада
    session.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.no >= NO_BASE).delete(synchronize_session=False)
    session.commit()


@pytest.fixture
def deal_id(db):
    from app.sales.models import SalesDeal
    row = db.query(SalesDeal.id).first()
    assert row, "в базе нет ни одной сделки — тест не на чем прогнать"
    return row[0]


def _set(deal_id, no, **kw):
    return LaunchPrepCreativeSet(deal_id=deal_id, no=no, **kw)


def test_two_common_sets_with_same_number_are_refused_by_db(db, deal_id):
    """Общий комплект — это publisher_id IS NULL, и обычный UNIQUE его не удержал бы."""
    db.add(_set(deal_id, NO_BASE + 1))
    db.commit()

    db.add(_set(deal_id, NO_BASE + 1))
    with pytest.raises(IntegrityError) as e:
        db.commit()
    assert "uq_lp_set_no" in str(e.value), (
        "сработало не то ограничение — проверить NULLS NOT DISTINCT в миграции")


def test_personal_set_may_repeat_the_number_of_a_common_one(db, deal_id):
    """Персональный комплект нумеруется независимо от общего — иначе счёт съедет."""
    from app.sales.models import SalesPublisher
    pub = db.query(SalesPublisher.id).first()
    assert pub, "в базе нет ни одной площадки"

    db.add(_set(deal_id, NO_BASE + 2))
    db.commit()
    db.add(_set(deal_id, NO_BASE + 2, publisher_id=pub[0]))
    db.commit()          # не должно упасть

    assert db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.no == NO_BASE + 2).count() == 2


def test_replaces_link_is_refused_when_origin_is_not_rework(db, deal_id):
    """Ссылка «что заменяет» имеет смысл только у доработки."""
    first = _set(deal_id, NO_BASE + 3)
    db.add(first)
    db.commit()

    db.add(_set(deal_id, NO_BASE + 4, origin='параллельный', replaces_set_id=first.id))
    with pytest.raises(IntegrityError) as e:
        db.commit()
    assert "ck_lp_set_replaces" in str(e.value)


def test_replaces_link_is_allowed_for_rework(db, deal_id):
    first = _set(deal_id, NO_BASE + 5)
    db.add(first)
    db.commit()

    db.add(_set(deal_id, NO_BASE + 6, origin='доработка', replaces_set_id=first.id))
    db.commit()          # не должно упасть


# ── словари значений: закреплены тестом, а не CHECK'ом ───────────────────────
def test_value_lists_are_pinned():
    """Опечатка в русском литерале не ловится типами — только этим списком."""
    assert TARGET_STATES == (
        'согласование', 'согласован', 'ерид получен', 'заведён в DSP',
        'в размещении', 'завершён', 'сверка завершена', 'архив',
        # Боковой выход, а не ступень: отказ площадки стоит последним, поэтому переход
        # в него разрешён с любой ступени, а обратно порядковое сравнение не пускает.
        'отказ площадки')
    # 'продление' добавлено 28.08.2026: комплект, скопированный с прошлой кампании.
    # Значение несёт два послабления сразу — трафик его не смотрит повторно, а площадка
    # отвечает «запуск разрешён», а не «согласовать креатив», — и оба должны иметь
    # видимое основание, иначе «ок» без проверки выглядит как ошибка.
    assert SET_ORIGINS == ('первичный', 'доработка', 'параллельный', 'продление')
    assert ERID_SOURCES == ('наш', 'площадки')
    assert REVIEW_KINDS == ('первичная_тт', 'трафики', 'площадка')
    assert REVIEW_VERDICTS == ('ок', 'на доработку', 'отказ'), (
        "«отказ» — третий исход, а не разновидность доработки: доработка ждёт новую "
        "версию, отказ закрывает площадку для этой кампании")
    assert 'авто' in REVIEW_SOURCES, (
        "'авто' отделяет машинный вердикт от человеческого: без него «эту пару никто "
        "не смотрел» уже не восстановить")
    assert 'продление' in REVIEW_SOURCES, (
        "перенесённая отметка трафика — НЕ 'авто': материал проверен, просто в прошлый "
        "период. Слить их значит потерять разницу между «никто не смотрел» и "
        "«смотрели в прошлой кампании»")


def test_public_projection_hides_our_three_steps_after_erid():
    """«Для площадки мы не детализируем после получения ЕРИД» (владелец)."""
    assert set(TARGET_STATE_PUBLIC) == set(TARGET_STATES), (
        "у состояния появился вариант без проекции наружу — площадка увидит пустоту")

    assert TARGET_STATE_PUBLIC['отказ площадки'] == 'отказ'

    after_erid = {TARGET_STATE_PUBLIC[s]
                  for s in ('ерид получен', 'заведён в DSP', 'в размещении')}
    assert after_erid == {'ЕРИД получен'}, "три наших состояния обязаны схлопнуться в одно"

    assert TARGET_STATE_PUBLIC['согласование'] != TARGET_STATE_PUBLIC['согласован'], (
        "до маркера состояния различимы: площадке важно, ждём мы её или уже её ответ учли")
